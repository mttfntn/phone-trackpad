# Security policy

## Supported versions

Only the latest release of Phone Trackpad receives fixes. It supports Windows and macOS with
Python 3.10 to 3.14.

## What counts as a security problem

Phone Trackpad controls the mouse and keyboard of the computer it runs on, so anything that lets
someone else do that is a security problem. For example: pairing without the PIN, reusing or
guessing a token, reaching files on the computer through the page, or making the helper run
code.

Known and documented: the page and the WebSocket use plain HTTP on the local network, so someone
who can watch the network traffic can read it (see the README's Security section).

## Reporting a problem

**Please don't open a public issue.** Report it privately instead: go to the repository's
**Security** tab and choose **Report a vulnerability**
([direct link](https://github.com/mttfntn/phone-trackpad/security/advisories/new)).

Please describe the problem and how to reproduce it. You'll get a reply as soon as possible, and
the fix will be released before the details are made public.
