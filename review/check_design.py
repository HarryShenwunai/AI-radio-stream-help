"""Local document/schema/package checks. Does not test external integrations."""
from pathlib import Path
import json,re,csv,hashlib
from urllib.parse import urlsplit,unquote
root=Path(__file__).resolve().parents[1];checks=[]
def check(name,value):
 if not value:raise AssertionError(name)
 checks.append({'check':name,'result':'passed'})
plan=(root/'docs/planning/revised-plan.md').read_text();comp=(root/'docs/research/zerolan-comparison.md').read_text()
check('ten planned requirements',set(re.findall(r'Q(\d\d)',plan))=={f'{i:02}' for i in range(1,11)})
with (root/'review/traceability.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
check('traceability IDs match',set(r['requirement'] for r in rows)=={f'Q{i:02}' for i in range(1,11)})
check('design baseline preserves unexecuted full-phase acceptance',all(r['status']=='NOT_RUN' for r in rows))
specs=json.loads((root/'review/test-specifications.json').read_text());check('design snapshot does not fabricate phase acceptance',specs['integration_tests_executed']==0 and all(t['actual_result'] is None for t in specs['tests']))
lo=[2,2,2,4,2,3];hi=[3,4,4,7,4,5]
check('base effort sum',(sum(lo),sum(hi))==(15,27));check('reserve-inclusive effort',(sum(lo)+3,sum(hi)+6)==(18,33));check('both optional extensions',(18+3+3,33+6+6)==(24,45))
check('critical branch discovery retained','dev' in comp and 'master' in comp and '最初' not in comp[:100])
check('TTS external-fork caveat retained','zerolan_api.py' in comp)
check('privacy boundary','公开会话不读取私人记忆' in plan)
check('approved route does not grant account or broadcast authorization','不代表已授权连接账号、游戏或公开播出' in plan)
check('naming remains undecided','未命名' in (root/'README.md').read_text())
missing=[]
for f in root.rglob('*.md'):
 # Verbatim upstream model cards include IPA notation that resembles links.
 if '.git' in f.parts or f.is_relative_to(root/'app/licenses'):continue
 for target in re.findall(r'\]\(([^\s)]+)\)',f.read_text()):
  if target.startswith(('http:','https:','mailto:','#')):continue
  local=(f.parent/unquote(target.split('#')[0])).resolve()
  if not local.exists():missing.append((str(f.relative_to(root)),target))
check('all owned local Markdown targets exist',not missing)
schema=json.loads((root/'contracts/interaction-v1.schema.json').read_text())
import jsonschema
jsonschema.Draft202012Validator.check_schema(schema)
v=jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker())
event={'event_id':'2a560da7-45c9-425a-ad9f-93574ff4b3bb','request_id':'26da9111-0fdd-45dd-9a0a-b7342044a40d','session_id':'fixture-private','channel':'private','source':'web','generation_id':'fixture-generation','kind':'user_text','created_at':'2026-11-12T12:00:00Z','payload':{'text':'测试'}}
v.validate(event);check('schema and synthetic example valid',True)
for extra in [{'role':'owner'},{'kind':'run_shell'}]:
 bad=dict(event,**extra);check('schema rejects unknown privilege field or kind '+str(list(extra)),bool(list(v.iter_errors(bad))))
files=[p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts]
banned={'.db','.sqlite','.gguf','.onnx','.bin','.pt','.pth','.wav','.mp3','.zip','.exe','.dmg'}
check('no weights runtime data or bundles',all(p.suffix.lower() not in banned and p.name not in {'api-key','.env'} for p in files))
check('no unusually large Git blobs',all(p.stat().st_size<2_000_000 for p in files))
report={'date':'2026-11-12','review':'separate self-review and local structural/schema checks; not independent personnel V&V','checks':checks,'upstream_or_platform_tests_executed':0,'current_local_execution':'phase1-tests.json','unresolved':['User hardware and budget','Live room/platform eligibility and exact danmuji','AR root and asset licenses','MC selected version/authorization','Runtime compatibility, Chinese voice quality and latency'],'manual_corrections':['MC dev bridge discovery replaces inference from master','Generic TTS placeholder distinguished from external fork service','HTTP chunk vs NDJSON frame distinction','Query class default UUID risk','No private/public shared history','No naming decision','Core effort and seven-day actions distinguished']}
(root/'review/design-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'checks_passed':len(checks),'upstream_or_platform_tests_executed':0,'current_local_execution':'review/phase1-tests.json','missing_links':missing},ensure_ascii=False))
