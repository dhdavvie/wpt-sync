import traceback
import os

from .. import log
from ..lock import constructor, SyncLock, mut
from ..base import entry_point
from ..gitutils import update_repositories
from ..env import Environment
from ..errors import AbortError
from ..commit import _apply_patch
from ..upstream import commit_message_filter, UpstreamSync

logger = log.get_logger(__name__)
env = Environment()


class PhabUpstreamSync(UpstreamSync):
    def __init__(self, git_gecko, git_wpt, process_name):
        super(PhabUpstreamSync, self).__init__(git_gecko, git_wpt, process_name)

        self._upstreamed_diff_head = None
        self._phabricator_diffs = []
        self._upstreamed_phabricator_diffs = None

    @classmethod
    @constructor(lambda args: ("upstream", args['bug']))
    def new(cls, lock, git_gecko, git_wpt, gecko_base, bug, diffs):
        sync = super(PhabUpstreamSync, cls).new(lock,
                                                git_gecko,
                                                git_wpt,
                                                bug=bug,
                                                gecko_base=gecko_base,
                                                gecko_head=gecko_base,
                                                wpt_base="origin/master",
                                                wpt_head="origin/master",
                                                )

        sync.phabricator_diffs = diffs
        return sync

    @classmethod
    def for_differential(cls, git_gecko, git_wpt, differential_id):
        """Find the PhabUpstreamSync process for a given Differential if there is one"""
        return False

    @property
    def upstreamed_phabricator_diffs(self):
        if (self._upstreamed_phabricator_diffs is None or
                self._upstreamed_diff_head != self.wpt_commits.head.sha1):
            self._upstreamed_phabricator_diffs = [
                wpt_commit.metadata["diff-url"].rsplit("=", 1)[1]
                for wpt_commit in self.wpt_commits
                if "diff-url" in wpt_commit.metadata]
            self._upstreamed_diff_head = self.wpt_commits.head.sha1
        return self._upstreamed_phabricator_diffs

    @mut()
    def move_commits(self):
        """Moves the commits from Phabricator to WPT"""
        # TODO In future need to have ability to check which commits need to be added when updating
        # a sync
        wpt_work = self.wpt_worktree.get()
        wpt_work.git.reset(hard=True)
        wpt_work.git.clean(f=True, d=True, x=True)

        for revision, diff in self.phabricator_diffs:
            self.add_diff(revision, diff)

    @mut()
    def add_diff(self, revision, diff, wpt_work=None):
        """Adds the Phabricator Diff to WPT as a git commit"""
        if wpt_work is None:
            wpt_work = self.wpt_worktree.get()

        # Setup metadata
        revision_url = env.config["phabricator"]["differential"]["base-url"] + str(revision["id"])
        diff_url = revision_url + "?id=%s" % diff['id']
        metdata = {
            "revision-url": revision_url,
            "diff-url": diff_url,
        }

        # If a file with the diff already exists, then this must've been applied already
        if os.path.exists(os.path.join(wpt_work.working_dir, str(diff['id']) + ".diff")):
            raise AbortError("Skipping due to existing patch")

        # Get the raw diff of the phabricator Diff object, and parse to remove any non wpt stuff
        raw_diff = env.phab.get_raw_diff(str(diff['id']))
        parsed_diff = parse_wpt_diff(raw_diff)

        # Apply the diff to wpt_work
        wpt_commit = _apply_patch(parsed_diff,
                                  revision['fields']['title'],
                                  str(diff['id']),
                                  wpt_work,
                                  metadata=metdata,
                                  msg_filter=commit_message_filter,
                                  src_prefix=env.config["gecko"]["path"]["wpt"])

        if wpt_commit:
            self.wpt_commits.head = wpt_commit

        return wpt_commit, True


def parse_wpt_diff(raw_diff, wpt_path=None):
    """Parses the raw diff of a Diff object so that it only contains changes to wpt"""
    if wpt_path is None:
        wpt_path = env.config["gecko"]["path"]["wpt"]

    # TODO Could miss someone moving a file into wpt, need to fix
    file_diffs = raw_diff.split('diff --git a/')
    rv = ["diff --git a/%s" % file_diff
          for file_diff in file_diffs
          if file_diff.startswith(wpt_path)]
    return "\n".join(rv)


def is_wpt_revision(revision):
    """Returns True if this Revision contains changes to wpt, otherwise False"""
    wpt_path = env.config["gecko"]["path"]["wpt"]
    commit_paths = env.phab.get_commit_paths(revision['id'])
    for path in commit_paths:
        if path.startswith(wpt_path):
            return True
    return False


@entry_point("upstream")
def new_phab_differential(git_gecko, git_wpt, differential_revision, base_rev=None,
                          repo_update=True, raise_on_error=True):
    if repo_update:
        update_repositories(None, git_wpt)

    # TODO will need to get entire stack instead of just the single revision in the future

    bug_id = int(differential_revision['fields']['bugzilla.bug-id'])
    differential_id = differential_revision['id']
    diff_id = differential_revision['fields']['diffPHID']
    diff = env.phab.get_diff(diff_id)

    if not is_wpt_revision(differential_revision):
        logger.info("This Revision doesn't affect wpt")
        return

    # If we already have a sync process for this then it is not a new differential
    if PhabUpstreamSync.for_differential(git_gecko, git_wpt, differential_id):
        return

    gecko_base = PhabUpstreamSync.gecko_landing_branch()

    # TODO Bug ID is probably not the best idea but still need to work on that
    # There is a data model issue where one Phabricator Revision stack can address multiple
    # Bugs, not sure what the best way to deal with this is yet.
    with SyncLock("upstream", None) as lock:
        sync = PhabUpstreamSync.new(lock,
                                    git_gecko,  # TODO this is actually useless, refactor out
                                    git_wpt,
                                    gecko_base,
                                    bug_id,
                                    [(differential_revision, diff)])

        with sync.as_mut(lock):
            try:
                sync.move_commits()
                sync.push_commits()
                sync.create_pr()
            except Exception as e:
                sync.error = e
                if raise_on_error:
                    raise
                traceback.print_exc()
                logger.error(e)
