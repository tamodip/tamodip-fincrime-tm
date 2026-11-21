# Build an alert-closing system

Start with `BRIEF.html`, which explains transaction monitoring, the four institutions, their rules and how you are scored. This file is the short version, with what you need while you build.

## The goal

Build a system that reads transaction monitoring alerts and **closes as many of them as it safely can**. When you finish, we run your system on 800 cases it has never seen, from the same four institutions, in the same format and under the same policies. The score on those unseen cases is what counts most, so build something that works from the policy and the evidence, not something that memorises these cases.

Closing safely means closing every case the evidence explains, and only those:

- **CLOSE** when the evidence explains all the activity the alerts raised.
- **RFI** (request for information) when nothing is suspicious yet and one specific document or answer from the customer would settle it. The reason must say what to ask for.
- **ESCALATE** to the MLRO when the activity is unexplained or there are signs of crime. Once there is suspicion, escalate rather than ask the customer.

A CLOSE on a case that needed an RFI or an escalation is the most costly mistake: it costs 10. Sending a case that could have been closed to an RFI or an escalation costs 3, so a system that escalates everything also scores badly.

## This folder

| Folder | Institution | Development cases |
|---|---|---|
| `institutions/bank/` | Bank | 1000 |
| `institutions/emoney/` | E-money firm | 1000 |
| `institutions/investment/` | Investment firm | 1000 |
| `institutions/payments_fx/` | Payments and FX firm | 1000 |
| `system/` | You write your system here | |
| `output/` | You write your system's answers on the development cases here | |

The development cases have no answers. Each institution folder has its own `POLICY.md`, which defines the verdicts, what a case is, the rules that institution runs with their limits, and the policy settings to apply. **The four policies differ.** The unseen cases come in folders with exactly the same files:

| File | What it holds |
|---|---|
| `POLICY.md` | The institution's SOP |
| `cases.jsonl` | One case per line: the customer, the review window, the alert IDs in the case and any held payment |
| `alerts.jsonl` | Each alert: its ID, the rule, what it measured and the transactions it fired on |
| `customers.jsonl` | Customer details and what they declared when they joined |
| `transactions.jsonl` | Transactions on each customer's accounts |
| `evidence.jsonl` and `evidence/` | Documents on file for each customer, one Markdown file per document |
| `previous_reviews.jsonl` | Earlier alert reviews for these customers |
| `internal_list.jsonl` | The institution's internal list |

## What to deliver

1. **`system/run`**, an executable we call as:

   ```
   system/run <institution folder> <output file>
   ```

   We pass full paths and run it from inside `system/`, so it must not depend on any other working directory. The institution folder's name is `bank`, `emoney`, `investment` or `payments_fx`, and it holds the files above. From this folder, for example: `system/run institutions/bank output/bank.jsonl`.

2. **One JSON line per case** in that folder's `cases.jsonl`, written to the output file. The line covers every alert in the case, because one verdict decides them all:

   ```json
   {"case_id": "BK-CS112964", "alert_ids": ["BK-AL4810357"], "verdict": "CLOSE", "reason_code": "LIST_MATCH_DIFFERENT_PARTY", "reason": "The joinery firm's director shares the listed person's name, but the company register gives a birth year of 1993, not 1972. The payment matches the firm's invoice for fitted wardrobes.", "evidence": ["REG-5461", "INV-7291", "BK-L37007"]}
   ```

   | Field | Type | What it holds |
   |---|---|---|
   | `case_id` | ID | The case, from `cases.jsonl` |
   | `alert_ids` | List of IDs | Every alert in the case |
   | `verdict` | Enum | `CLOSE`, `RFI` or `ESCALATE` |
   | `reason_code` | Enum | The main ground for the verdict, from the table below. It must belong to the verdict given |
   | `reason` | Free text | Two to four sentences naming the specific facts and documents relied on. For an RFI, exactly what to ask the customer for |
   | `evidence` | List of IDs | The documents, transactions or list entries relied on, exactly as their IDs appear in the files |

   Every case needs exactly one line; a missing case counts as an escalation.

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

3. **`system/README.md`**: how the system decides, which model it uses if any, and how long and how much a run of 200 cases takes.

4. **`output/<institution>.jsonl`** for all four institutions, made by running your system on the development cases. These must be your system's output, not answers written by hand.

## Rules

- The system must work on cases it has never seen. Do not put case IDs, customer names, amounts, document IDs or verdicts from the development cases into the system.
- When it runs, the system reads only the institution folder it is given and writes only the output file and files inside `system/`.
- Use the standard library of Python 3 or Node.js, or shell. Do not rely on packages that need installing.
- The system may call a language model, but only through the OpenRouter chat completions API (`https://openrouter.ai/api/v1/chat/completions`), reading the key from the `OPENROUTER_API_KEY` environment variable. Use your own key while you build; when we test the system we set ours. Keep a run of 200 cases under 30 minutes and under about four US dollars.

## How it is assessed

We run your system **five times** on the unseen cases and assess it on four things:

1. **Results with the fewest mistakes.** Close as many closable cases as possible while making as few wrong decisions as possible. A wrongful close (closing a case that needed an RFI or an escalation) is the worst mistake and should never happen. We report wrongful closes, the share of closable cases closed, and a cost per case where a wrongful close costs 10, not closing a closable case costs 3, and an RFI on a case that should escalate costs 3.
2. **Explainable evidence.** Every verdict needs a reason code and a reason that names the specific facts it rests on, and `evidence` must list the IDs of the documents, transactions or list entries relied on. Cited IDs must exist in the case's files, and the deciding ones should be among them.
3. **The same results every time.** The five runs must give the same verdicts and reason codes, and ideally the same evidence. Make the system deterministic: for example fixed rules, a model at temperature 0, and no randomness that changes a verdict.
4. **Precision on verdict and reason.** For every case with the right verdict, the reason is scored on three things: whether `evidence` includes the documents that decide the case, whether the reason gives the grounds the right answer relies on, and whether it names this case's own documents, people and amounts rather than wording that would fit any case. A correct verdict with a generic or wrong reason scores little.

**The score, out of 100.**

| Part | Weight | What counts |
|---|---|---|
| Unseen cases | 60% | Verdicts 60%, reasons 40% |
| Development cases | 20% | Verdicts 60%, reasons 40% |
| Reproducibility | 20% | Same verdict and reason code in all five runs |

Verdicts score the share of the cost of escalating every case that your system saves, so escalating everything scores 0. Reproducibility points grow with the unseen score, so repeating poor results earns little. We also run your system once more on the development cases to check that your development answers came from it.
