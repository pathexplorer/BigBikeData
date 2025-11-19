#!/bin/bash
export SMTP_SERVER=localhost
export SMTP_PORT=1025
export SMTP_USER=fakeuser
export SMTP_PASSWORD=fakepassword
export SENDER_EMAIL=sender@example.com
echo $SMTP_SERVER
echo $SMTP_PORT
echo $SMTP_USER
echo $SMTP_PASSWORD
echo $SENDER_EMAIL