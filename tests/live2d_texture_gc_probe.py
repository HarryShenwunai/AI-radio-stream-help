"""Controlled real-WebGL negative probe for wrapper/Pixi texture lifetime mismatch.

Uses the existing independent Core harness, without touching product/runtime code.
Aged timestamps and short GC threshold deliberately accelerate the same lifetime gate.
"""
from pathlib import Path
import hashlib
import json
import shlex
import sys

import live2d_original_core_check as harness

original_arguments = list(sys.argv[1:])
with_product_fix = '--with-product-fix' in sys.argv
if with_product_fix:
    sys.argv.remove('--with-product-fix')
    if '--product-adapter' not in sys.argv:
        raise SystemExit('--with-product-fix requires the actual --product-adapter bundle')
original_render = harness.RENDER_CHECK
harness.RENDER_CHECK = r'''async modelURL=>{
 const result=await (''' + original_render + r''')(modelURL);
 const {app,model}=__original,renderer=app.renderer,gl=renderer.gl,source=model.textures[0].source,handle=model.cachedGlTextures[0];
 if(!gl.isTexture(handle))throw Error('Positive control: initial model texture is invalid');
 const useFix=FIX_LITERAL;if(useFix){if(typeof CompanionLive2D?.refreshActiveTextures!=='function')throw Error('Actual product texture lifetime fix missing');renderer.runners.prerender.add({prerender(){CompanionLive2D.refreshActiveTextures(renderer,model);}});}
 const canvas=document.createElement('canvas');canvas.width=canvas.height=16;const unused=CompanionLive2DRuntime.PIXI.Texture.from(canvas);unused.source.autoGarbageCollect=true;const unusedHandle=renderer.texture.getGlSource(unused.source).texture;
 const aged=performance.now()-1000;source._gcLastUsed=aged;
 for(let i=0;i<3;i++){model.update(1000/60);renderer.render(app.stage);}
 const afterRender=source._gcLastUsed,beforeGC=gl.isTexture(handle);
 unused.source._gcLastUsed=aged;renderer.gc.maxUnusedTime=500;renderer.gc.run();
 const afterGC=gl.isTexture(handle);while(gl.getError()!==gl.NO_ERROR){}
 model.update(1000/60);renderer.render(app.stage);const error=gl.getError(),pixels=__pixels();
 const unusedCollected=!gl.isTexture(unusedHandle);
 let reload=null;if(useFix){const oldHandle=model.cachedGlTextures[0];source.unload();model.update(1000/60);renderer.render(app.stage);const nextHandle=model.cachedGlTextures[0],nextPixels=__pixels();reload={handleReplaced:nextHandle!==oldHandle,validNewHandle:gl.isTexture(nextHandle),oldHandleDeleted:!gl.isTexture(oldHandle),pixels:nextPixels};}
 const observed={useFix,unusedCollected,unusedExplicitlyGarbageCollectible:unused.source.autoGarbageCollect,reload,method:'Controlled negative: deliberately age this active model texture by 1000ms, render it three times, then run the real Pixi GC with 500ms threshold; no replacement GL/Core/texture implementation',aged,afterRender,lastUsedRefreshed:afterRender>aged,beforeGC,afterGC,glErrorAfterDeletedBind:error,pixels};
 if(useFix){if(!observed.lastUsedRefreshed||!beforeGC||!afterGC||error!==0||pixels.colored<100||!unusedCollected||!reload?.handleReplaced||!reload.validNewHandle||!reload.oldHandleDeleted||reload.pixels.colored<100||reload.pixels.error!==0)throw Error('Actual product lifetime fix failed: '+JSON.stringify(observed));}else if(observed.lastUsedRefreshed||!beforeGC||afterGC||error!==gl.INVALID_OPERATION||pixels.colored!==0)throw Error('Expected lifetime counterexample not reproduced: '+JSON.stringify(observed));
 return {...result,gc_counterexample:observed};
}'''
harness.RENDER_CHECK = harness.RENDER_CHECK.replace('FIX_LITERAL', 'true' if with_product_fix else 'false')
if '--probe-pixels' not in sys.argv:
    sys.argv.append('--probe-pixels')
output = Path(sys.argv[sys.argv.index('--output') + 1])
harness.main()
report = json.loads(output.read_text())
report['status'] = 'product_fix_regression_passed' if with_product_fix else 'expected_counterexample_reproduced'
report['acceptance_complete'] = False
report['checks'].pop('required_parameters_have_actual_visible_pixel_effects', None)
report['checks']['active_texture_real_gc_lifecycle'] = 'product fix passed with unused collection and real reupload' if with_product_fix else 'counterexample reproduced'
report['scope'] = 'Controlled actual owner Core + real WebGL texture lifetime regression; actual product fix applied only if explicitly requested; unused texture remains collectible and manual unload must reupload; accelerated age/threshold, not a wall-clock endurance measurement'
report['harness_variant'] = {'file': str(Path(__file__).resolve()), 'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'render_javascript_sha256': hashlib.sha256(harness.RENDER_CHECK.encode()).hexdigest()}
report['reproduce_command'] = 'PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright ' + shlex.join([sys.executable, str(Path(__file__).resolve()), *original_arguments])
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'counterexample': report['render']['gc_counterexample']}, ensure_ascii=False))
