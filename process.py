#!/usr/bin/python
import urllib2, json, sqlite3, yaml, smtplib, sys
from email.mime.text import MIMEText
try:
    info = yaml.load(open(sys.argv[1],'r'))
except IndexError:
    print 'usage: %s configuration_file' % sys.argv[0]
    sys.exit(1)
except yaml.YAMLError, exc:
    print 'Error in configuration file:', exc
    sys.exit(2)

def sendbadmail(b, info):
    # TODO: Remove debugging override
    print 'Sending error notice to', b
    b = 'david@d2j.us'
    message = MIMEText(info['badtext'])
    message['Subject'] = info['badsubj']
    message['From'] = info['from']
    message['To'] = b
    info['s'].sendmail(info['from'], [b], message.as_string())

def sendgoodmail(voter, info):
    # TODO: Remove debugging override
    print 'Sending successful vote notice to', ';'.join(voter['emails'])
    voter['emails'] = ['david@d2j.us', 'election@d4tm.org']
    if len(voter['roles']) > 1:
        info['goodtext'] += '\nYour vote has been recorded for each of your %d roles.' % len(voter['roles'])
    message = MIMEText(info['goodtext'])
    message['Subject'] = info['goodsubj']
    message['From'] = info['from']
    message['To'] = ', '.join(voter['emails'])
    info['s'].sendmail(info['from'], voter['emails'], message.as_string())


# Connect to the database
conn = sqlite3.connect(info['db'])
c = conn.cursor()

# Create a password manager
baseurl = info['baseurl'] + '/api/v3/forms/'
formurl = baseurl + info['formname']
password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
password_mgr.add_password(None, baseurl, info['apicode'], 'footastic')
handler = urllib2.HTTPBasicAuthHandler(password_mgr)

# Connect to the mail server
print 'connecting to', info['mailserver']
info['s'] =  smtplib.SMTP(info['mailserver'], info.get('mailport', 25))
info['s'].login(info['from'], info['mailpw'])

# Create "opener"
opener = urllib2.build_opener(handler)

#fields = opener.open(formurl + '/fields.json').read()
#fields = json.loads(fields)['Fields']
#print fields
#print len(fields)

# For this round, we're going to ignore the fields and use hardcoded values

ecount = json.load(opener.open(formurl + '/entries/count.json'))['EntryCount']
ecount = int(ecount)


fvote = 'Field6'
fvalidation = 'Field8'
fname = 'Field10'
femail = 'Field13'
fields = (fvote, fvalidation, fname, femail)

enext = 0
pagesize = 100
newvoters = {}
badvoters = {}

while enext <= ecount:

    entries = json.load(opener.open(formurl + '/entries.json?pageStart=%d&pageSize=%d' % (enext, pagesize)))['Entries']
    enext += pagesize

    for e in entries:
        (vote, validation, name, email) = [e[f] for f in fields]
        c.execute('SELECT first, last, title, area, division, email, vote, confirmed FROM voters WHERE validation=?', (validation,))
        results = c.fetchall()
        if results:
            for res in results:
                (first, last, title, area, division, realemail, oldvote, confirmed) = res
                if confirmed and oldvote == vote:
                    continue  # Ignore votes already registered
                dbname = '%s %s' % (first, last)
                role = ' '.join((' %s%s %s' % (division, area, title)).split())
                print role, dbname, 'votes', vote
                # Normalize email addresses
                realemail = realemail.lower()
                email = email.lower()
                
                if realemail <> email:
                    print 'email mismatch: db has %s, entered %s' % (realemail, email)
                if oldvote and vote <> oldvote:
                    print 'vote change from %s to %s' % (oldvote, vote)
                    confirmed = False  # Need to confirm any changes
                c.execute('UPDATE voters SET vote = ? WHERE validation=?', (vote, validation))
                if not confirmed:
                    if realemail in newvoters:
                        newvoters[realemail]['roles'].append(role)
                        newvoters[realemail]['emails'].append(email)
                    else:
                        newvoters[realemail] = {'roles': [role], 'emails': [email],
                                 'validation': validation}
                              
                    badvoters.pop(realemail, None)  # A good vote overrides a bad one
        else:
            print 'Fail!', name, email, validation
            badvoters[email] = email

conn.commit()  # Commit votes

# If there were any validation fails, send out the error
for b in badvoters:
    sendbadmail(b, info)

# Now, send out emails to successful voters; every time we send an email,
# commit that it's been done.
for b in newvoters:
    sendgoodmail(newvoters[b], info)
    c.execute('UPDATE voters SET confirmed = 1 WHERE validation = ?', (newvoters[b]['validation'],))
    conn.commit() # Commit this one

conn.close()

