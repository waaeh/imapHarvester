# IMAP Harvester

Did you setup lots of emails for spam or malware and want to gather them in one place easily? IMAP Harvester opens a connection in IDLE mode for multiple email addresses and waits asynchronously for notifications from the server. 

Emails are saved in a mailbox structure viewable by e.g. your preferred IMAP client.



## Installation & Configuration

1. Install all requirements
```
pip install -r requirements.txt
```

2. Configure the traps settings as well as the path to save the gathered emails in imapHarvester.json