from phabricator import Phabricator as Phab
from .. import log


logger = log.get_logger(__name__)


class Phabricator(object):

    def __init__(self, config):
        self.phab = Phab(host='https://phabricator.services.mozilla.com/api/',
                         token=config['phabricator']['token'])
        self.phab.update_interfaces()

    def add_comment(self, differential_id, message):
        self.phab.differential.revision.edit(objectIdentifier=differential_id,
                                             transactions=[{"comment": message}])

    def get_revision(self, revision_id):
        """Return the Differential Revision by the given ID, if it exists"""
        result = self.phab.differential.revision.search(constraints={'phids': [revision_id]})
        if result.get('data'):
            return result['data'][0]
        else:
            logger.error("Could not find Revision '%s'" % revision_id)

    def get_repo(self, repo_id):
        result = self.phab.repository.query(phids=[repo_id])
        if result:
            return result[0]
        else:
            print("Could not find Repo '%s'" % repo_id)

    def get_diff(self, diff_id):
        """Return the Diff object by the given ID, if it exists"""
        result = self.phab.differential.diff.search(constraints={'phids': [diff_id]})
        if result.get('data'):
            return result['data'][0]
        else:
            logger.error("Could not find Diff '%s'" % diff_id)

    def get_raw_diff(self, diff_id):
        result = self.phab.differential.getrawdiff(diffID=diff_id)
        if result:
            return str(result.response)
        else:
            logger.error("%s returned unexpected result: %s" % (diff_id, result))

    def get_feed(self, before=None):
        """Return a feed of events. Can be from a specified event onwards."""
        feed = []

        def chrono_key(feed_story_tuple):
            return int(feed_story_tuple[1]["chronologicalKey"])

        # keep fetching stories from Phabricator until there are no more stories to fetch
        while True:
            result = self.phab.feed.query(before=before, view='text')
            if result.response:
                results = sorted(result.response.items(), key=chrono_key)
                feed.extend(results)
                if len(results) == 100 and before is not None:
                    # There may be more events we wish to fetch
                    before = int(results[-1]["chronologicalKey"])
                    continue
            break
        return feed

    def get_commits_paths(self, revision_id):
        result = self.phab.differential.getcommitpaths(revision_id=revision_id)
        if result:
            return result.response
        else:
            logger.error("Error getting commit paths for Revision %d" % revision_id)


class MockPhabricator(Phabricator):

    def __init__(self, config):
        pass

    def get_revision(self, revision_id):
        return {"fields": {"authorPHID": "PHID-USER-dzqqj4kg6v774z2yiaeh", "status": {"color.ansi": "green", "name": "Accepted", "value": "accepted", "closed": False}, "bugzilla.bug-id": "1607530", "testPlan": "", "title": "Bug 1607530 - Fixing lifetime issues in promise closures;r?nika", "isDraft": False, "summary": "", "repositoryPHID": "PHID-REPO-saax4qdxlbbhahhp2kg5", "diffPHID": "PHID-DIFF-mqq4lwiwy4ipqvaewtwt", "policy": {"edit": "PHID-PROJ-njo5uuqyyq3oijbkhy55", "view": "public"}, "dateCreated": 1578483417, "dateModified": 1578507542, "holdAsDraft": False}, "phid": "PHID-DREV-ff55ctxc7qdl3w44lqu6", "type": "DREV", "id": 59092, "attachments": {}}

    def get_diff(self, diff_id):
        return {"fields": {"authorPHID": "PHID-USER-dzqqj4kg6v774z2yiaeh", "refs": [{"type": "branch", "name": "default"}, {"identifier": "bc5880b621d585ca49be49e07ee14dd32153c01b", "type": "base"}], "revisionPHID": "PHID-DREV-ff55ctxc7qdl3w44lqu6", "dateCreated": 1578502144, "repositoryPHID": "PHID-REPO-saax4qdxlbbhahhp2kg5", "policy": {"view": "public"}, "dateModified": 1578502147}, "phid": "PHID-DIFF-mqq4lwiwy4ipqvaewtwt", "type": "DIFF", "id": 215120, "attachments": {}}

    def get_repo(self, repo_id):
        return {"monogram": "rMOZILLACENTRAL", "remoteURI": "https://hg.mozilla.org/mozilla-unified/", "phid": "PHID-REPO-saax4qdxlbbhahhp2kg5", "staging": {"prefix": "phabricator", "supported": False, "uri": None}, "name": "mozilla-central", "encoding": "UTF-8", "uri": "https://phabricator.services.mozilla.com/source/mozilla-central/", "isHosted": False, "isImporting": False, "callsign": "MOZILLACENTRAL", "vcs": "hg", "id": "1", "isActive": True, "description": ""}

    def get_raw_diff(self, diff_id):
        return """diff --git a/dom/ipc/ContentParent.cpp b/dom/ipc/ContentParent.cpp
--- a/dom/ipc/ContentParent.cpp
+++ b/dom/ipc/ContentParent.cpp
@@ -961,30 +961,33 @@
   RefPtr<LaunchPromise> launchPromise = p->LaunchSubprocessAsync(aPriority);
   MOZ_ASSERT(launchPromise);

+  // Until the new process is ready let's not allow to start up any
+  // preallocated processes. In case of success, the blocker is removed
+  // when we receive the first `idle` message. In case of failure, we
+  // cleanup manually in the `OnReject`.
+  PreallocatedProcessManager::AddBlocker(p);
+
+  nsAutoString remoteType(aRemoteType);
   return launchPromise->Then(
       GetCurrentThreadSerialEventTarget(), __func__,
diff --git a/testing/web-platform/tests/acid/acid3/empty.css b/testing/web-platform/tests/acid/acid3/empty.css
--- /dev/null
+++ b/testing/web-platform/tests/acid/acid3/empty.css
@@ -0,0 +1,8 @@
+<!DOCTYPE HTML><html><head><title>FAIL</title><style>
+<!-- this file is sent as text/html, not text/css, which is why it is
+     called "empty.css" despite the following lines -->
+
+  body { background: white; color: black; }
+  h1 { color: red; }
+
+</style><body><h1>FAIL</h1></body></html>
"""

    def get_commit_paths(self, revision_id):
        return ['dom/ipc/ContentParent.cpp', 'testing/web-platform/tests/acid/acid3/empty.css']
