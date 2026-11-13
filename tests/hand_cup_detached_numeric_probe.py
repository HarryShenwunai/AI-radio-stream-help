"""Measure, without accepting, any detached cup float differences under Body.

This diagnostic preserves exact coordinate differences and ULP counts. It does
not change the strict ROOT guard or infer that every observed difference is a
visible functional defect. No WebGL/art/Windows acceptance is claimed.
"""
import argparse
import base64
import datetime
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script
from hand_cup_metamorphic_check import sha,runtime_binding_files,write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','grip-guides','runtime-dir','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    model=Path(args.model).resolve();guide=Path(args.grip_guides).resolve();runtime=Path(args.runtime_dir).resolve()
    setting=json.loads(model.read_text());moc=model.parent/setting['FileReferences']['Moc']
    cup=json.loads(guide.read_text())['landmarks']['grip_r_cup']['drawable_id'];core=installed_script(runtime,'core')
    paths=[model,moc,guide,Path(__file__).resolve(),*runtime_binding_files(runtime)]
    sources={str(path):sha(path)for path in paths}
    with sync_playwright()as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        page=browser.new_page();page.add_script_tag(content=core.read_text())
        measured=page.evaluate(r'''input=>{
          const C=Live2DCubismCore,bytes=Uint8Array.from(atob(input.moc),x=>x.charCodeAt(0));
          if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('actual Core rejected MOC');
          const moc=C.Moc.fromArrayBuffer(bytes.buffer),model=C.Model.fromMoc(moc),p=model.parameters,d=model.drawables,c=model.canvasinfo;
          const index=d.ids.indexOf(input.cup);if(index<0)throw Error('Missing actual cup mesh');
          const data=new DataView(new ArrayBuffer(4));
          function ordered(value){data.setFloat32(0,value);const n=data.getUint32(0);return (n&0x80000000)?(~n>>>0):((n|0x80000000)>>>0);}
          function pose(values){p.values.set(p.defaultValues);for(const [id,value]of Object.entries({...values,ParamCupHold:0})){
            const i=p.ids.indexOf(id);if(i<0)throw Error('No actual parameter '+id);p.values[i]=value;}
            model.update();return Array.from(d.vertexPositions[index]);}
          function diff(a,b){const changes=[];for(let i=0;i<a.length;i++)if(a[i]!==b[i])changes.push({component:i,
            baseline:a[i],actual:b[i],delta_core:b[i]-a[i],delta_source_px:(b[i]-a[i])*c.PixelsPerUnit,
            ulps:Math.abs(ordered(a[i])-ordered(b[i]))});
            return {changed_components:changes.length,max_abs_source_px:Math.max(0,...changes.map(x=>Math.abs(x.delta_source_px))),
              max_ulps:Math.max(0,...changes.map(x=>x.ulps)),first_changes:changes.slice(0,8)};}
          const rest=pose({}),cases=[{}, {ParamBodyAngleX:.5,ParamBreath:.025},
            {ParamBodyAngleX:.75,ParamBreath:.05}, {ParamBodyAngleX:-5,ParamBodyAngleY:5,ParamBodyAngleZ:-5,ParamBodyLean:5,ParamProportion:-5,ParamBreath:.25}];
          const result={coreVersion:C.Version.csmGetVersion(),ppu:c.PixelsPerUnit,cupId:input.cup,rest_opacity:d.opacities[index],cases:[]};
          for(const values of cases){const a=pose(values),b=pose(values);result.cases.push({parameters:values,against_default:diff(rest,a),same_pose_repeat:diff(a,b),opacity:d.opacities[index]});}
          model.release();moc._release();return result;
        }''',{'moc':base64.b64encode(moc.read_bytes()).decode(),'cup':cup})
        browser.close()
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'measured_not_an_acceptance',
        'scope':'actual Core only, exact source-pixel and Float32 ULP diagnosis; no production guard changed',
        'sources':sources,'sources_unchanged':all(sha(Path(path))==digest for path,digest in sources.items()),'measurement':measured}
    write_report(args.output,report);print(json.dumps(report['measurement'],ensure_ascii=False))


if __name__=='__main__':main()
