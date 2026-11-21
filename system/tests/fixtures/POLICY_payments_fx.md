# Payments and FX firm: transaction monitoring SOP

A UK payments and foreign exchange firm. Business clients fund their account from their own bank, convert currency and pay suppliers and staff abroad. An alert on an outgoing payment holds that payment until a decision is made.

## Your task

For every case in `cases.jsonl`, decide one verdict and write the reason for it. Use only the files in this folder.

## Verdicts

- **CLOSE**: the activity is explained and fits what the institution knows about the customer. A held payment is released.
- **RFI** (request for information): there is no suspicion yet, and one specific document or answer from the customer would settle the case. The reason must say what to ask for.
- **ESCALATE** (escalate to the MLRO): the activity is unexplained or there are signs of crime. The MLRO decides whether to report it.

Once there is suspicion, escalate. Do not send the customer an RFI at that point: asking them questions risks tipping them off, which is an offence.

Closing a case that needed an RFI or an escalation is the most costly mistake. Close only when the evidence explains the activity.

## What a case is

A case is one held outgoing payment, with every alert raised on it. For money coming in, a case is one client over the review window. One case gets one verdict, even when several rules fired.

## Rules this institution runs

| Rule | Name | Fires when |
|---|---|---|
| TM01 | Activity exceeds the expected profile | Money received over 30 days is more than 2 times the monthly share of the expected annual payment volume the client declared. |
| TM02 | Rapid movement of funds | Over 10 days, at least 80% of the money received from anyone other than the client (£2,000.00 or more) is paid out within 48 hours of arriving. Card spending is not counted as paid out. |
| TM03 | Repeated transactions below a threshold | 3 or more payments to the same beneficiary, each between £9,000.00 and £9,999.99, within 10 days. Payments of £10,000.00 or more need an invoice on file. |
| TM04 | Many-to-one or one-to-many payments | The client pays more than 25 different beneficiaries within 30 days. |
| TM06 | Unexpected higher-risk corridor | Payments of £5,000.00 or more within 30 days to or from a higher-risk country the customer did not declare. |
| TM07 | Dormant account reactivation | £5,000.00 or more moves after 180 days with no activity on the account. |
| TM08 | Third-party funding or payout | Funding of £1,000.00 or more comes from an account whose holder name is not the client's. |
| TM22 | Counterparty on an internal list | A payer, recipient or company officer matches an entry on the internal list by name, address, date of birth or identifier. A match on one detail alone does not prove it is the same party. |

## Policy settings

- Currency: pounds sterling. Amounts in other currencies are also given in pounds.
- Cash reporting threshold: £10,000.00.
- Higher-risk countries as of 1 October 2026: Afghanistan, Belarus, Democratic Republic of the Congo, Haiti, Iran, Iraq, Lebanon, Libya, Mali, Myanmar, North Korea, Russia, Somalia, South Sudan, Syria, Venezuela, Yemen.
- When transfers between the customer's own accounts explain activity at 5 times the declared income or volume or more, send an RFI for an updated expected income or volume. Below 5 times, close.
- An account in the customer's own name elsewhere counts as their own account only when a document on file shows the customer holds it.
- Payments of £10,000 or more to anyone other than the client need an invoice or contract on file before they are released. Transfers to accounts in the client's own name do not.
- Round amounts, a shared device, IP address or contact details, a recipient added the same day, and crypto or gambling counterparties add context. None of them raises an alert on its own.
- The internal list (`internal_list.jsonl`) holds earlier internal cases, exited customers and blocked banks. Close a list match only when the evidence shows the counterparty is a different party. If nothing on file settles it either way and nothing else is concerning, send an RFI. If the evidence shows the listed party is the counterparty or controls it, escalate.
- An earlier review covers only what it describes. It does not explain new or larger activity.

## Files

| File | What it holds |
|---|---|
| `cases.jsonl` | One row per case: the customer, the review window, the alerts in the case and any held payment |
| `alerts.jsonl` | Each alert: the rule, what it measured and the transactions it fired on |
| `customers.jsonl` | Customer details and what they declared at onboarding |
| `transactions.jsonl` | Transactions on the customers' accounts, usually the last 120 days and longer for dormant accounts |
| `evidence.jsonl` and `evidence/` | Documents on file for each customer, one Markdown file per document |
| `previous_reviews.jsonl` | Earlier alert reviews for these customers |
| `internal_list.jsonl` | The institution's internal list |

## What to submit

One JSON line per case in `cases.jsonl`, written to the output file you are given:

```json
{"case_id": "...", "alert_ids": ["..."], "verdict": "CLOSE", "reason_code": "INVOICE_MATCHES", "reason": "Two to four sentences naming the facts and documents relied on. For an RFI, what to ask the customer for.", "evidence": ["IDs of the documents, transactions or list entries relied on"]}
```

- `alert_ids`: every alert in the case.
- `verdict`: `CLOSE`, `RFI` or `ESCALATE`.
- `reason_code`: the main ground for the verdict, from the table below. It must belong to the verdict given.
- `reason`: free text naming the specific facts and documents relied on.
- `evidence`: IDs exactly as they appear in the files.

| Verdict | Reason code | Use it when |
|---|---|---|
| CLOSE | `COLLECTION_DOCUMENTED` | A documented collection made on behalf of named people explains the payments |
| CLOSE | `BUSINESS_RECORDS_RECONCILE` | Business records, such as takings or collection reports, reconcile to the activity |
| CLOSE | `DOCUMENTED_EVENT` | A documented one-off event, such as a sale, an inheritance or a payout, explains the funds |
| CLOSE | `INVOICE_MATCHES` | An invoice, contract or payment file matches the amount, payee and date |
| CLOSE | `OWN_ACCOUNT` | The money moved between accounts the customer is shown to hold |
| CLOSE | `GROUP_COMPANY` | The counterparty is a verified company in the same group |
| CLOSE | `THIRD_PARTY_DOCUMENTED` | A documented relationship explains a third-party payer |
| CLOSE | `REFUND_OF_EARLIER_PAYMENT` | The money is a refund of an earlier payment |
| CLOSE | `RETURNING_CUSTOMER` | A verified customer resumed using a dormant account |
| CLOSE | `LIST_MATCH_DIFFERENT_PARTY` | The evidence shows the counterparty is not the listed party |
| CLOSE | `WITHIN_PROFILE` | The activity fits the customer's declared profile or instructions |
| RFI | `RFI_PURPOSE_DOCUMENTS` | Ask for documents showing what the payments were for |
| RFI | `RFI_BUSINESS_RECORDS` | Ask for the business records behind the activity |
| RFI | `RFI_SOURCE_OF_FUNDS` | Ask for proof of where the money came from |
| RFI | `RFI_COUNTERPARTY_DETAILS` | Ask who the counterparty is and what the payment was for |
| RFI | `RFI_UPDATED_PROFILE` | Ask for an updated expected income or volume |
| ESCALATE | `ESC_MULE_ACTIVITY` | The account receives and passes on other people's money for someone else |
| ESCALATE | `ESC_STRUCTURING` | Transactions were split to stay under a threshold |
| ESCALATE | `ESC_UNEXPLAINED_FUNDS` | The money has no credible explanation and was moved on |
| ESCALATE | `ESC_PASS_THROUGH` | Money passes through with no credible purpose, often to linked parties |
| ESCALATE | `ESC_INVOICE_MISMATCH` | The invoices do not support the payments |
| ESCALATE | `ESC_HIGH_RISK_CORRIDOR` | Unexplained payments to or from a higher-risk country |
| ESCALATE | `ESC_ACCOUNT_MISUSE` | Someone other than the customer appears to control or use the account |
| ESCALATE | `ESC_THIRD_PARTY_FUNDING` | Unrelated third parties fund the account or receive money from it |
| ESCALATE | `ESC_EARLY_REDEMPTION` | Fund units are bought and quickly sold back to move money |
| ESCALATE | `ESC_LISTED_PARTY` | The counterparty is the listed party or is controlled by it |

Verdicts are scored first, with wrongful closes costing most. For cases with the right verdict, the reason is checked against the grounds the right answer relies on.
