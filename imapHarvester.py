#!/usr/bin/python3


# Opens a connection in IDLE mode for multiple email addresses
# and wait asynchronously for notifications from the server


import email
import json
import logging
import mailbox
import random
import threading

from datetime import datetime, timedelta
from collections import deque

# pip install imapclient
from imapclient import IMAPClient


JSON_CONFIG_FILE = 'imapHarvester.json'


class Helper:
    _LOADED = False
    MAILDIR_PATH = None
    CONFIG = None

    @staticmethod
    def get_config():
        if not Helper.CONFIG:
            with open(JSON_CONFIG_FILE, 'r') as f:
                Helper.CONFIG = json.load(f)
        
        Helper.MAILDIR_PATH = Helper.CONFIG['maildir_path']
        return Helper.CONFIG

    @staticmethod
    def store_message(msg):
        mdir = mailbox.Maildir(Helper.MAILDIR_PATH)
        return mdir.add(msg)



class EmailTrap(threading.Thread):
    def __init__(self, json_cfg):
        self.logger = logging.getLogger("imapclient-"+json_cfg['user'])
        self.logger.debug("Starting __init__()...")
        threading.Thread.__init__(self)
        self.shutdown = None
        self.errors = deque(maxlen=5)

        self.user = json_cfg['user']
        self.password = json_cfg['password']
        self.server = json_cfg['server']
        self.json_cfg = json_cfg
        self.has_new_msgs = None
        self.imap_client = None


    def stop(self):
        self.logger.info('Received stop() request...')
        self.shutdown.set()

    def init(self):
        self.logger.info('Starting init() for thread {}...'.format(self.name))
        self.shutdown = threading.Event()
        try:
                self.imap_client = IMAPClient(self.server, use_uid=True)
                # Issues with passwords having non-ascii characters => all is utf-8 encoded
                self.imap_client.login(self.user, self.password.encode('utf-8'))
                self.imap_client.select_folder('INBOX')
        except Exception as e:
                self.logger.error('exception {} for user {}'.format(e, self.user))
                self.stop()


    def run(self):
        self.logger.debug("Starting run()...")
        self.init()

        while not self.shutdown.is_set():
            if len(self.errors) == self.errors.maxlen:
                # We stop the IMAP connection to this mailbox if 5 errors occured in the last 3 hours
                if datetime.now() - self.errors[0] < timedelta(hours=3):
                    self.logger.error('Too many exceptions for user {} - shutting down now - {}'.format(self.user, self.errors))
                    self.stop()
            try:
                responses = None
                if self.has_new_msgs is not False:
                    self.process_msgs()

                self.has_new_msgs = False
                self.imap_client.idle()
                # Waiting loops of 5 min (60*5) - 10 min is too long for some email providers
                # Others providers will check idling every 2 minutes or so
                self.logger.info("Idling...")
                loop = 0
                while loop < 60 and not responses and not self.shutdown.is_set():
                    loop += 1
                    responses = self.imap_client.idle_check(timeout=5)
                if responses:
                    self.logger.info("Received following response(s): {}".format(responses))
                    if not (len(responses) == 1 and responses[0][0] == b'OK' and responses[0][1] == b'Still here'):
                        self.has_new_msgs = True
                #self.logger.info("Server sent:", str(responses) if responses else "nothing")
                self.imap_client.idle_done()
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error('exception {} for user {} - trying to re-init()'.format(e, self.user))
                self.errors.append(datetime.now())
                self.init()

        if self.imap_client:
            self.imap_client.logout()
        self.stop()
        self.logger.warning("Logout succeeded!")
    

    def process_msgs(self):
        messages = self.imap_client.search('UNSEEN')
        self.logger.warning("Retrieved {} unseen msg(s)...".format(len(messages)))
        for uid, message_data in self.imap_client.fetch(messages, 'RFC822').items():
            self.logger.info("Fetching msg uid {}...".format(uid))
            email_message = email.message_from_bytes(message_data[b'RFC822'])
            email_message.add_header("X-FOSR-Retrieved-Email", self.user)
            email_message.add_header("X-FOSR-Retrieved-Timestamp", datetime.now().isoformat())
            #self.logger.info(uid, str(email_message.get('From')), str(email_message.get('Subject')))
            res = Helper.store_message(email_message)
            self.logger.warning("Stored msg uid {} under maildir key {}".format(uid, res))

    def get_status(self):
        status = 'STOPPED' if self.shutdown.is_set() else 'running'
        count_err = len(self.errors)
        last_err = ''
        if count_err:
            last_err = "- last error at {}".format(self.errors[0].isoformat())

        return "{} / {} - {} error(s) {}".format(status, self.is_alive(), count_err, last_err)



def stats(traps):
    for trap in traps:
        print("{} - {} - {}".format(trap.user, trap.name, trap.get_status()))


def restart(traps):
    print("Restarting all stopped traps...")
    new_traps = []
    for trap in traps:
        if trap.shutdown.is_set():
            trap.stop()
            trap = EmailTrap(trap.json_cfg)
            trap.setDaemon(True)
            trap.start()
        new_traps.append( trap )
    return new_traps

def kill_trap(traps):
    random_index = random.randrange(len(traps))
    print("Killing random trap - index {} - for test purposes...".format(random_index))
    traps[random_index].stop()


def changeLogLevel(verbose):
    if verbose:
        logging.getLogger().setLevel(logging.getLogger().getEffectiveLevel() - 10) 
    else:
        logging.getLogger().setLevel(logging.getLogger().getEffectiveLevel() + 10)
    print("Logging level set to {}".format( logging.getLevelName(logging.getLogger().getEffectiveLevel()) )) 




def main():
    logging.basicConfig(level=logging.WARN, format='%(asctime)s %(levelname)s %(name)s %(message)s')

    traps = []
    config = Helper.get_config()
    for trap in config['traps']:
       traps.append( EmailTrap(trap) )

    for trap in traps:
        logging.info("Starting trap {}".format(trap.user))
        trap.setDaemon(True)
        trap.start()

    try:
        while True:
            key = input()
            if key in ['r', 'R']:
                traps = restart(traps)
            if key == 'V':
                changeLogLevel(False)
            if key == 'v':
                changeLogLevel(True)
            if key in ['s', 'S']:
                stats(traps)
            if key in ['k', 'K']:
                kill_trap(traps)

    except KeyboardInterrupt:
        for trap in traps:
            logging.warning("Stopping trap {}...".format(trap.user))
            trap.stop()
        for trap in traps:
            trap.join()
    
    logging.warning("Clearnly stopped everything!")



if __name__ == '__main__':
    main()
