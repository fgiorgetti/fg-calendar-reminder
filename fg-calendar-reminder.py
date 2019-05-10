from __future__ import print_function
import datetime
import pickle
import os.path
import os
import time
import subprocess
import logging
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


"""
This is a daemon that monitors the events from your primary Google Calendar.
You must create a project that requests access to Calendar API and save the
credentials.json file along with the fg-calendar-reminder.py file.

Follow instructions from:
https://developers.google.com/calendar/quickstart/python

And save the "credentials.json" along with fg-calendar-reminder.py.

Adjust the settings below to match your needs and run the daemon.

Requirements:
* python >= 3.7
* pip install -r requirements.txt
"""


# Time to expire notification
NOTIFY_TIME_MS = '50000'
# Minutes to trigger notification
MINUTES_LEFT = [1, 5, 10]
# Sleep hours - list of (start, end) pairs
SLEEP_HOURS = [(20, 6)]
# Command (list) to play sound notification
AUDIO_PLAY_CMD = ["play", "5glasses.ogg"]

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# Initialize logging
logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s [%(levelname)s] (%(pathname)s:%(lineno)s) - %(message)s')
LOGGER = logging.getLogger(__name__)


class Alert(object):
    """
    Object that holds alert info to be displayed
    """
    def __init__(self, summary, date, minutes_left):
        self.summary = summary
        self.date = date
        self.minutes_left = minutes_left

    def __str__(self):
        return "In %d minutes [%s] -> %s" % (self.minutes_left, self.date, self.summary)


def create_daemon():
    """
    Starts a daemon to monitor events every minute (second 0)
    playing a sound and displaying a gnome notification at the
    pre-defined amount of minutes left.

    :return:
    """
    try:
        pid = os.fork()
    except OSError as ex:
        LOGGER.error(ex)
        raise Exception("%s [%d]" %(ex.strerror, ex.errno))

    if pid == 0:
        # Lead the session without a controlling terminal
        os.setsid()
    else:
        # Exit parent
        LOGGER.info("Daemon has been started (PID=%s)" % pid)
        os._exit(0)

    try:
        while True:
            monitor_events()
            wait_time = 60 - datetime.datetime.now().second
            LOGGER.debug("Sleeping for %d" % wait_time)
            time.sleep(wait_time)
    except SystemExit as ex:
        LOGGER.warn("Exiting. Reason: %s" % ex)
        pass
    except Exception as ex:
        LOGGER.error("Unexpected exception: %s" % ex)
        return 1

    LOGGER.info("Exiting fg-calendar-reminder")
    return 0


def monitor_events():
    """
    Method retrieves list of next events and display notification (notify-send) and play
    a notification sound if minutes left to the event match what is on the MINUTES_LEFT list.
    If current hour is within the sleep hours, nothing will be done.
    :return:
    """
    service = create_service()

    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    now_datetime = datetime.datetime.now()

    # if sleep hours, skip
    for start, end in SLEEP_HOURS:
        cur_hour = now_datetime.hour
        skip = False
        if end < start and (start <= cur_hour or cur_hour <= end):
            skip = True
        elif start <= cur_hour <= end:
            skip = True
        if skip:
            LOGGER.debug("Sleep hour [%d] - skipping" % now_datetime.hour)
            return

    # Call the Calendar API
    LOGGER.debug('Getting the upcoming 10 events')
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                          maxResults=10, singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        LOGGER.debug('No upcoming events found.')

    # Looping through event list and validate if an event is happening soon
    alerts = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        LOGGER.debug(start, event['summary'])
        start_datetime = datetime.datetime.fromisoformat(start)
        mins_left = round((start_datetime.replace(tzinfo=None) - now_datetime).seconds / 60)
        if mins_left in MINUTES_LEFT:
            alerts.append(Alert(event['summary'], start, mins_left))

    # No alerts to show
    if not alerts:
        LOGGER.debug("No alerts found")
        return

    # Displaying reminder
    LOGGER.debug("Displaying reminder")
    if len(alerts) == 1:
        alert = alerts[0]
        subprocess.Popen(['notify-send', '-t', NOTIFY_TIME_MS, "Upcoming event: %s" % alert.summary[:50], alert.__str__()])
    else:
        subprocess.Popen(['notify-send', '-t', NOTIFY_TIME_MS,
                          'Upcoming events: %d' % len(alerts),
                          "\n".join([a.__str__() for a in alerts])])
    # Play audio an alert
    LOGGER.debug("Playing audio")
    subprocess.Popen(AUDIO_PLAY_CMD)


def create_service():
    """
    Creates an instance of the service (using the provided credentials.json)
    :return:
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('calendar', 'v3', credentials=creds)
    return service


def main():
    create_daemon()


if __name__ == '__main__':
    main()
