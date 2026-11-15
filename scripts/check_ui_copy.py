"""Static interface contracts: no seeded chatter/examples; controls outside preview.

This rejects concrete regressions. It does not grade writing or model answers.
"""
from html.parser import HTMLParser
from pathlib import Path
import ast
import re

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN=('来啦。想聊什么','现在这样的声音，你听起来舒服吗','给性格一个起点','给你留个安静的位置','今日份小小问候','稍后继续','本场主题尚未填写','尚未置顶提问','圈出本节的核心问题')

class PreviewControls(HTMLParser):
 def __init__(self):super().__init__();self.stack=[];self.bad=False
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if any(self.stack) and tag in {'button','input','select','textarea','a'}:self.bad=True
  if tag not in {'img','input','meta','link','br','hr','source','area','base','embed','param','wbr'}:self.stack.append(attrs.get('id')=='room' or any(self.stack))
 def handle_endtag(self,tag):
  if self.stack and tag not in {'img','input','meta','link','br','hr'}:self.stack.pop()

def check(sources):
 problems=[]
 for path,text in sources.items():
  for phrase in FORBIDDEN:
   if phrase in text:problems.append((path,'C01',phrase))
  if re.search(r'placeholder\s*=\s*["\'][^"\']*(?:例如|比如|示例)',text):problems.append((path,'C02','example placeholder'))
 room=sources.get('app/static/room.html','');parser=PreviewControls();parser.feed(room)
 if parser.bad:problems.append(('app/static/room.html','C03','interactive control inside preview'))
 studio=sources.get('app/static/studio.js','')
 if 'personality-choices' in studio:problems.append(('app/static/studio.js','C04','preset personality copy'))
 server=sources.get('app/server.py','')
 if server:
  tree=ast.parse(server)
  for node in ast.walk(tree):
   if isinstance(node,ast.FunctionDef) and node.name=='init_profile':
    values=[c.value for c in ast.walk(node) if isinstance(c,ast.Constant) and isinstance(c.value,str)]
    if 'welcome' in values and any('INSERT INTO messages' in v for v in values):problems.append(('app/server.py','C05','seeded assistant welcome'))
 return problems

def main():
 paths=[*sorted((ROOT/'app/static').glob('*.html')),*sorted((ROOT/'app/static').glob('*.js')),ROOT/'app/server.py']
 result=check({str(p.relative_to(ROOT)):p.read_text(encoding='utf-8') for p in paths})
 for row in result:print(': '.join(row))
 print('UI copy and preview boundaries: '+('FAIL' if result else 'PASS'));return 1 if result else 0
if __name__=='__main__':raise SystemExit(main())
