# Payment Entry bank-account lookup

The company bank-account lookup runs for Pay and Receive entries with a company
and company account. Only the latest lookup for the current document and inputs
may apply its result. Clearing an input or switching to Internal Transfer
supersedes an outstanding lookup.

The bank-account recursion guard stays active through the asynchronous field
change and is released on completion or failure. Request errors retain normal
Frappe error handling. This recovery does not grant access to Bank Account;
commercial entitlements and native permissions remain authoritative.

Run the callback, recovery, and request-race regressions with Node.js 18 or newer:

```sh
node --test tests/js/payment_entry_bank_account.test.js
```
