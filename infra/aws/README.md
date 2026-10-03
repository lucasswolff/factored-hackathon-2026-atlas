# AWS judge deployment

The stack has been deployed in `us-east-2` using the dedicated CLI profile
`factored-hackathon-2026`. Its public URL is available with
`terraform -chdir=infra/aws output -raw judge_url`. It is currently **enabled**
(`enabled=true`) for browser testing. A disabled health check returns HTTP 429.
Do not substitute another AWS profile silently.

## What the stack creates

Terraform manages a Python Lambda function, its public HTTPS Function URL, a
DynamoDB on-demand table, a seven-day CloudWatch log group, a scoped execution
role and policy, and two function-URL permissions. It also installs two saved
Logs Insights queries, a server-error metric filter, and console alarms for
HTTP 5xx responses and Lambda throttling. It sends only the
team-written demo fixtures and the public offer fact sheet to Lambda. No
organizer CSVs, source customer rows, Snowflake credentials, or local `.env`
files are packaged. The generated `advisor.zip` is ignored by Git.

The function starts with `enabled=false`, which sets reserved concurrency to
zero. AWS then throttles invocations without running the advisor. Set
`enabled=true` shortly before judging to use the account's unreserved Lambda
capacity. This account currently has a regional concurrency quota of ten, so a
future high-traffic deployment needs a quota increase. Returning to `false`
stops the app while preserving the same URL and
the mock-action table. Terraform destroy removes both the URL and the table;
it is not the normal off switch. The shared DynamoDB daily cap defaults to
200 **provider request attempts** across all visitors and Lambda instances.
A corrective retry consumes a second slot; deterministic application and
precheck steps consume none. Once exhausted, the app returns HTTP 429 before
making another model request.

The judge URL is intentionally public; only synthetic profiles can be selected.
Sessions expire after two hours without a visitor action; keeping a page open
does not hold a Lambda invocation open.
The reviewer queue still requires its separate reviewer code. This is a
hackathon demo, not customer authentication or a production lending service.

## Automatic code deployment from protected main

The [GitHub Actions workflow](../../.github/workflows/deploy-advisor.yml) tests
source-data-free advisor paths on pull requests to `main`. After a pull request
is squash-merged, the resulting `push` to protected `main` repeats those tests,
builds a Lambda ZIP from the explicit [file manifest](lambda_files.txt), and
uploads it to the existing function. It waits for the update, compares the live
code hash with the ZIP hash, and checks `/healthz`. The Function URL stays the
same. A failed test prevents deployment; a failed post-deployment health check
marks the workflow failed but does not automatically roll back the Lambda code.

GitHub Actions assumes a short-lived AWS role through OIDC. The trust policy is
bound to this repository's immutable owner/repository IDs and `main` ref. Its
policy permits only `UpdateFunctionCode` and the Lambda reads needed to verify
the advisor function. It cannot read the hosted secret parameter, access the
table, or change function settings. The role ARN is not a credential and no AWS
key is stored in GitHub. Terraform bootstraps this role and provider; the live
AWS account has already received them. Terraform manages infrastructure and
ignores later Lambda ZIP/hash drift so a local `terraform apply` does not
overwrite a release from `main`.

Local edits, feature-branch pushes, and pull requests do not update the site.
Only a passing workflow on a `main` push deploys code. Source-backed tests that
need organizer CSVs still run locally; the CI suite uses fictional hosted
fixtures because the source CSVs are deliberately absent from the public repo.
The workflow is activated when its PR is merged into `main`; until then, the
current live code remains the previously deployed local package.

## Credentials and state

The deployment uses a **Standard SecureString** Systems Manager parameter
named `/factored/advisor/hosted` in `us-east-2`, encrypted
with the account's `aws/ssm` key. Its JSON value must have exactly these
private entries:

```json
{
  "ANTHROPIC_API_KEY": "<your-provider-key>",
  "ADVISOR_REVIEW_CODE": "<random-code-at-least-20-characters>"
}
```

The parameter has already been created. For a new deployment, create it through
the AWS console or a private script; **do not**
put its value in Terraform variables, a shell command, a commit, or the public
submission. Terraform receives only the parameter *name*, so secrets do not
enter its state. The Lambda role can read only this parameter and its own
DynamoDB table and logs. A different parameter name can be passed with
`-var='secret_parameter_name=/path/name'`.

Terraform state is local and ignored by Git. Keep a private backup if you need
to manage the same deployment from another computer. The `.terraform.lock.hcl`
dependency lock file is safe to commit.

## Local checks and on/off commands

The following first three commands read AWS identity/configuration but do not
create or change AWS resources. The explicit profile avoids using the default
or `atlas-market-user` credentials.

```bash
terraform -chdir=infra/aws init -backend=false
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws plan -var='enabled=false'
```

For a fresh account, the first apply can be run disabled:

```bash
terraform -chdir=infra/aws apply -var='enabled=false'
```

For the evaluation window:

```bash
terraform -chdir=infra/aws apply -var='enabled=true'
terraform -chdir=infra/aws output -raw judge_url
```

Afterward:

```bash
terraform -chdir=infra/aws apply -var='enabled=false'
```

Check the real URL with a fresh browser before sharing it. The Lambda URL is
HTTPS without purchasing a domain. Keep the app disabled outside judging and
do not rely on AWS Budget emails as an immediate shutoff mechanism.

The first live smoke test confirmed a direct Argentina session, precheck
consent, mock-application creation and read-back, reviewer-only queue access,
and a Portuguese Summit product answer using the public fact sheet. The URL
was then disabled and returned HTTP 429. It was later re-enabled for user
testing; `/` and `/healthz` both returned HTTP 200. This is a smoke test, not a load test
or independent bilingual review.

## Operating visibility

In CloudWatch Logs Insights, open the saved queries
`factored-advisor/requests` and `factored-advisor/model-attempts` against the
seven-day log group. The first shows response counts and p50/p95 duration by
endpoint and status; the second shows provider-request attempts per hour. Logs
contain only fixed endpoint names, status, duration, and an internal route code.
They omit chat text, selected persona, customer fields, session cookies,
application references, and credentials. CloudWatch also displays the
`factored-advisor-server-errors` and `factored-advisor-lambda-throttles` alarms.
These alarms have **no notification destination**; the operator must inspect
them in the console. They do not shut off the function or enforce a dollar
budget. The DynamoDB daily provider-attempt limit is the active model-usage
guardrail; AWS and Anthropic account spend settings remain separate.

## Cost boundary

This is pay-per-use infrastructure: no provisioned servers, NAT gateway,
load balancer, domain, or provisioned Lambda concurrency. The Function URL has
no separate endpoint fee. Lambda has monthly free usage, but it is shared with
any other account usage. DynamoDB on-demand **request** charges can apply even
when the table's storage is within its free allowance. CloudWatch logs are
retained seven days. A Standard SSM parameter has no additional parameter
storage charge. Claude usage is outside AWS and is bounded by the app's daily
answer counter, not by AWS credits. A 200-attempt cap is not a dollar-denominated
spending limit: Sonnet bills by input and output tokens, so the provider
account's credits and spend limit still need checking. The AWS account-specific
credit expiry and whether all future usage is credit-eligible must be checked
in Billing before relying on credits.
