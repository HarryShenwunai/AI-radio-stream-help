"""Actual product WebGL pixel diagnosis of detached identity-grid differences.

Test-only render visibility filter hides non-cup drawables, preserving genuine
Core vertices/parameters and the real shader/texture/GL. No production policy,
MOC, pixel data or guard is edited. This isolates cup rasterization from moving
body occlusion; an actual one-source-pixel CupX shift is the negative control.
"""
import argparse,base64,datetime,json,os
from pathlib import Path
from hand_cup_metamorphic_check import ROOT,HOOK,OWN,PRODUCT,archive,recorded_browser,runtime_binding_files,runtime_files,sha,write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','grip-guides','runtime-dir','output','evidence-dir'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();os.environ['COMPANION_LIVE2D_RUNTIME']=str(Path(args.runtime_dir).resolve())
    from playwright.sync_api import sync_playwright
    from test_character_http import CharacterHTTPTests
    model,guide=Path(args.model).resolve(),Path(args.grip_guides).resolve();files=runtime_files(model)
    cup=json.loads(guide.read_text())['landmarks']['grip_r_cup']['drawable_id']
    paths=files+[guide,Path(__file__).resolve()]+[ROOT/name for name in OWN+PRODUCT]+runtime_binding_files(Path(args.runtime_dir).resolve())
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING',
        'scope':'diagnostic real product cup-only render visibility filter, actual Core geometry, real WebGL readback; not complete-rig acceptance',
        'sources':{str(path):sha(path)for path in paths},'page_errors':[]}
    evidence=Path(args.evidence_dir).resolve();evidence.mkdir(parents=True,exist_ok=True)
    fixture=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
    try:
        with sync_playwright()as pw,recorded_browser(pw,evidence)as(browser,context,page):
            page.add_init_script(HOOK);page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            base='http://127.0.0.1:'+str(fixture.server.server_port);page.goto(base);page.wait_for_function('()=>CompanionApp.core.get().state!==null')
            role=page.evaluate('()=>CompanionApp.core.scope().character_id');headers={'X-Companion':'local-app'}
            response=page.request.post(base+'/api/characters/assets/import',headers=headers,data={'character_id':role,'format':'live2d','model':{'filename':'actual-detached-pixel-probe.zip','data_base64':base64.b64encode(archive(model,files)).decode()}})
            assert response.ok,response.text();asset=response.json()['asset']
            response=page.request.post(base+'/api/characters/assets/activate',headers=headers,data={'character_id':role,'asset_id':asset['id']});assert response.ok,response.text()
            page.evaluate('()=>CompanionApp.core.refresh(true)');page.wait_for_function('()=>CompanionApp.scene.ready',timeout=60000)
            page.evaluate((ROOT/'tests/hand_cup_browser.mjs').read_text());page.evaluate('asset=>__handCup.init(asset)',asset)
            page.evaluate('''cup=>{const app=__actualPixiApps.find(a=>a.stage?.children?.some(c=>c.internalModel)),model=app.stage.children.find(c=>c.internalModel),core=model.internalModel.coreModel,raw=core.getModel(),index=raw.drawables.ids.indexOf(cup);
              if(index<0||raw.drawables.maskCounts[index]!==0)throw Error('Requires actual unmasked cup drawable');
              window.__restoreCupVisibility={core,original:core.getDrawableOpacity};
              core.getDrawableOpacity=function(i){return raw.drawables.ids[i]===cup?__restoreCupVisibility.original.call(this,i):0;};
              window.__cupPixels=()=>{app.renderer.render(app.stage);const gl=app.renderer.gl,data=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);
                gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,data);const error=gl.getError();
                if(!window.__cupBaseline){window.__cupBaseline=data;return {error,baseline:true,alpha_pixels:Array.from(data).filter((v,i)=>i%4===3&&v>8).length};}
                let changed=0,max=0;for(let i=0;i<data.length;i+=4){let different=false;for(let j=0;j<4;j++){const delta=Math.abs(data[i+j]-__cupBaseline[i+j]);max=Math.max(max,delta);different||=delta!==0;}if(different)changed++;}
                return {error,changed_pixels:changed,max_channel_delta:max};};}''',cup)
            page.evaluate('()=>__handCup.productPose({ParamCupHold:0})');report['baseline']=page.evaluate('()=>__cupPixels()')
            assert report['baseline']['error']==0 and report['baseline']['alpha_pixels']>100
            report['repeat_same_pose']=page.evaluate('()=>__cupPixels()')
            assert report['repeat_same_pose']['changed_pixels']==0
            cases=[]
            for values in ({'ParamBodyAngleX':.5,'ParamBreath':.025},{'ParamBodyAngleX':.75,'ParamBreath':.05},
                    {'ParamBodyAngleX':-5,'ParamBodyAngleY':5,'ParamBodyAngleZ':-5,'ParamBodyLean':5,'ParamProportion':-5,'ParamBreath':.25}):
                page.evaluate('v=>__handCup.productPose({...v,ParamCupHold:0})',values)
                pixels=page.evaluate('()=>__cupPixels()');assert pixels['error']==0
                cases.append({'parameters':values,'actual_gl':pixels})
            report['body_cases']=cases;page.screenshot(path=str(evidence/'TEST_ONLY-cup-isolated-body-case.png'))
            page.evaluate('()=>__handCup.productPose({ParamCupHold:0,ParamCupX:1})')
            report['one_source_pixel_cup_x_negative']=page.evaluate('()=>__cupPixels()')
            assert report['one_source_pixel_cup_x_negative']['error']==0 and report['one_source_pixel_cup_x_negative']['changed_pixels']>0
            page.evaluate('()=>{__restoreCupVisibility.core.getDrawableOpacity=__restoreCupVisibility.original;delete window.__restoreCupVisibility;__handCup.dispose();}')
            assert not report['page_errors'],report['page_errors'];report['status']='measured_not_an_acceptance'
    except Exception as error:
        import traceback
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
    finally:
        fixture.tearDown();report['sources_unchanged']=all(Path(path).is_file()and sha(Path(path))==digest for path,digest in report['sources'].items())
        write_report(args.output,report)
    print(json.dumps({key:value for key,value in report.items()if key!='sources'},ensure_ascii=False))


if __name__=='__main__':main()
