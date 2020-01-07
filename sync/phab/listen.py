import time
import re
from phab import Phabricator
import newrelic.agent

from .. import log
from ..tasks import handle


logger = log.get_logger(__name__)

RE_EVENT = re.compile("[0-9]{5,}:")
RE_COMMIT = re.compile("(committed|accepted|added a reverting change for) r[A-Z]+[a-f0-9]+:")


class PhabEventListener(object):

    ignore_list = ["added inline comments to D",
                   "added a comment to D",
                   "added a reviewer for D",
                   "added reviewers for D",
                   "removed a reviewer for D",
                   "removed reviewers for D",
                   "requested review of D",
                   "requested changes to D",
                   "added a subscriber to D",
                   "added a project to D",
                   "edited reviewers for D",
                   "updated the summary of D",  # Maybe useful to upstream info?
                   "accepted D",  # Maybe useful to upstream info?
                   "retitled D",  # Maybe useful to upstream info?
                   "blocking reviewer(s) for D",
                   "planned changes to D",
                   "updated subscribers of D",
                   "resigned from D",
                   "changed the edit policy for D",
                   "removed a project from D",
                   "updated D",
                   "changed the visibility for D",
                   "updated the test plan for D"]

    event_mapping = {
        "updated the diff for D": "commit",
        "created D": "opened",
        "closed D": "closed",
        "abandoned D": "abandoned",
        "added a reverting change for D": None,  # Not sure what this is yet
        "reopened D": "commit",  # This may need its own event type
    }

    def __init__(self, config):
        self.running = True
        self.timer_in_seconds = config['phabricator']['listener']['interval']
        self.latest = None

        self.phab = Phabricator(config)

    def run(self):
        # Run until told to stop.
        while self.running:
            feed = self.get_feed()
            self.parse(feed)
            time.sleep(self.timer_in_seconds)

    @newrelic.agent.background_task(name='feed-fetching', group='Phabricator')
    def get_feed(self, before=None):
        if self.latest and before is None:
            before = int(self.latest['chronologicalKey'])

        return map(self.map_feed_tuple, self.phab.get_feed(before=before))

    @newrelic.agent.background_task(name='feed-parsing', group='Phabricator')
    def parse(self, feed):
        # Go through rows in reverse order, and ignore first row as it has the table headers
        for event in feed:

            if RE_COMMIT.search(event['text']):
                # This is a commit event, ignore it
                continue

            # Split the text to get the part that describes the event type
            event_text = RE_EVENT.split(event['text'])[0]

            # Check if this is an event we wish to ignore
            if any(event_type in event_text for event_type in PhabEventListener.ignore_list):
                continue

            # Map the event text to an event type so we know how to handle it
            event['type'] = self.map_event_type(event_text, event)
            if event['type'] is None:
                continue

            # Add the event to the queue, and set this as the latest parsed
            handle.apply_async(("phabricator", event))
            self.latest = event

    @staticmethod
    def map_event_type(event_text, event):
        # Could use compiled regex expression instead
        for event_type, mapping in PhabEventListener.event_mapping.items():
            if event_type in event_text:
                return mapping

        logger.warning("Unknown phabricator event type: %s" % event_text)
        newrelic.agent.record_custom_event("unknown_phabricator_event", params={
            "event_text": event_text,
            "event": event,
        }, application=newrelic.agent.application())

    @staticmethod
    def map_feed_tuple(feed_tuple):
        story_phid, feed_story = feed_tuple
        feed_story.update({"storyPHID": story_phid})
        return feed_story


def run_phabricator_listener(config):
    logger.info("Starting Phabricator listener")
    listener = PhabEventListener(config)
    listener.run()


class MockPhabricator(Phabricator):

    def __init__(self, *args, **kwargs):
        self.feed = None
        pass

    def update_interfaces(self):
        pass
