"""Run a firmware ELF on Simantic Cloud Sim (POST /v1/runs) and fail the step if it fails."""
import base64, json, os, re, sys, time, urllib.error, urllib.request

env = os.environ
api = env.get('API_URL') or 'https://cloud.simantic.com'
key = env.get('API_KEY', '')
if not key:
    sys.exit('::error::api-key is empty. Add your smtc_ key as a repository secret (SIMANTIC_API_KEY).')


def call(method, path, body=None):
    req = urllib.request.Request(api + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                                          'User-Agent': 'simantic-embedded-ci-action'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f'::error::Simantic API {e.code} on {method} {path}: {e.read().decode()}')


run = {'mcu': env['MCU'],
       'firmware': {'base64': base64.b64encode(open(env['ELF_PATH'], 'rb').read()).decode()},
       'uart_encoding': env.get('UART_ENCODING') or 'ascii'}
if env.get('SIMULATED_SECONDS'):
    run['simulated_seconds'] = float(env['SIMULATED_SECONDS'])
run_id = call('POST', '/v1/runs', run)['id']
print(f'Run {run_id} queued')

status = 'queued'
while status not in ('succeeded', 'failed', 'canceled'):
    time.sleep(2)
    r = call('GET', f'/v1/runs/{run_id}')
    if r['status'] != status:
        status = r['status']
        print(f'Run {run_id} {status}')

result = call('GET', f'/v1/runs/{run_id}/result') if r['exit_code'] is not None else {}
output = result.get('output') or ''
print('::group::Simulator console'); print(result.get('log') or ''); print('::endgroup::')
print('--- UART output ---'); print(output)
with open(env.get('OUTPUT_FILE') or 'simantic-output.txt', 'w') as f:
    f.write(output)

failure = None
if status != 'succeeded':
    failure = f'run {status}: {r["error"] or "exit code " + str(r["exit_code"])}'
elif env.get('EXPECT') and not re.search(env['EXPECT'], output):
    failure = f'UART output does not match expect pattern {env["EXPECT"]!r}'

with open(env.get('GITHUB_STEP_SUMMARY') or os.devnull, 'a') as s:
    s.write(f'### Simantic {env["MCU"]}: {"❌ " + failure if failure else "✅ passed"}\n\n'
            f'Run `{run_id}`\n\n```\n{output[-20000:]}\n```\n')
with open(env.get('GITHUB_OUTPUT') or os.devnull, 'a') as o:
    o.write(f'run-id={run_id}\nexit-code={r["exit_code"]}\n')
if failure:
    sys.exit(f'::error::Simantic {failure}')
