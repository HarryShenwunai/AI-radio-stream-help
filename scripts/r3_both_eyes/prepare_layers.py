from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter
import numpy as np,json
from scipy.interpolate import PchipInterpolator
P=Path(__file__).resolve().parents[2]/'.build/r3-both-eyes'
for k in ['both_closed_clean','both_white_clean']:
 (P/(k+'.png')).write_bytes(b''.join(x.read_bytes() for x in sorted(P.glob(k+'-[0-9]*'))))
master=Image.open(P.parent/'r3-motion-revision/source/master.png').convert('RGB')
clean={k:Image.open(P/(k+'.png')).convert('RGB').resize((490,390),Image.Resampling.LANCZOS) for k in ['both_open_clean','both_closed_clean','both_white_clean']}
iris=Image.open(P/'full_iris.png').convert('RGBA');iris=iris.crop(iris.getbbox())
configs={
 'R':{'box':[700,410,810,500],'upper':[(25.5,42),(29,35),(34,29),(41,26),(48,26.5),(56,30),(64,35),(72,41),(77,47)],'lower':[(25.5,42),(32,43),(42,46),(52,49),(61,52),(68,53),(73,51),(77,47)],'iris':[740,445,36,38],'gaze':[3.2,1.6]},
 'L':{'box':[565,380,685,470],'upper':[(15,30),(25,22),(39,22),(52,26),(65,35),(78,47),(86,53)],'lower':[(15,30),(25,38),(39,45),(52,49),(65,53),(78,54),(86,53)],'iris':[614,417,38,40],'gaze':[3.5,1.8]},
}
for side,c in configs.items():
 box=c['box'];x0,y0,x1,y1=box;size=(x1-x0,y1-y0);w,h=size
 orig=master.crop(box)
 crops={k:im.crop((x0-340,y0-300,x1-340,y1-300)) for k,im in clean.items()}
 u=np.array(c['upper']);l=np.array(c['lower']);xs=np.linspace(u[0,0],u[-1,0],150)
 upper=PchipInterpolator(u[:,0],u[:,1]);lower=PchipInterpolator(l[:,0],l[:,1])
 poly=list(zip(xs,upper(xs)))+list(zip(xs[::-1],lower(xs[::-1])))
 mask=Image.new('L',(w*4,h*4));ImageDraw.Draw(mask).polygon([(int(x*4),int(y*4)) for x,y in poly],fill=255);mask=mask.resize(size,Image.Resampling.LANCZOS)
 closedmask=mask.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(3))
 sclera=crops['both_white_clean'].convert('RGBA');sclera.putalpha(mask);sclera.save(P/(side+'Sclera.png'))
 ir=Image.new('RGBA',size);cx,cy,iw,ih=c['iris'];ir.alpha_composite(iris.resize((iw,ih),Image.Resampling.LANCZOS),(round(cx-x0-iw/2),round(cy-y0-ih/2)));rgba=np.array(ir);oy,ox=np.mgrid[:h,:w];distance=np.sqrt(((ox-(cx-x0))/(iw/2))**2+((oy-(cy-y0))/(ih/2))**2)
 confidence=np.clip((.99-distance)/.22,0,1)
 original_rgb=np.array(orig)
 rgba[:,:,:3]=np.uint8(rgba[:,:,:3]*(1-confidence[:,:,None])+original_rgb*confidence[:,:,None])
 ir=Image.fromarray(rgba).filter(ImageFilter.GaussianBlur(.25));ir.save(P/(side+'Iris.png'))
 lid=crops['both_closed_clean'].convert('RGBA')
 yy0,xx0=np.mgrid[:h,:w]
 shade=np.clip((yy0-20)/32,0,1) if side=='L' else np.clip((yy0-18)/37,0,1)
 shade=(.63+.37*shade) if side=='L' else (.90+.10*shade)
 rgba=np.array(lid);rgba[:,:,:3]=np.uint8(rgba[:,:,:3]*shade[:,:,None]);lid=Image.fromarray(rgba)
 lid.putalpha(closedmask);lid.save(P/(side+'Lid.png'))
 # Original foreground pixels retain the bangs without freezing the pupil.
 yy,xx=np.mgrid[:h,:w];top=upper(np.clip(xx,u[0,0],u[-1,0]))
 foreground=np.maximum(1-np.array(closedmask)/255,np.clip((top-yy)/5,0,1))
 if side=='L':
  # Keep the original opaque fringe and wisps over the reconstructed eye.
  leftedge=np.interp(yy,[0,20,27,35,45,55,90],[48,48,44,41,36,30,10])
  hairleft=np.clip((leftedge-xx+2)/4,0,1)
  foreground=np.maximum(foreground,hairleft)
  lum=np.array(orig).mean(axis=2)
  strands=np.clip((100-lum)/25,0,1)
  foreground=np.maximum(foreground,strands*(xx>58))
 front=orig.convert('RGBA');front.putalpha(Image.fromarray(np.uint8(np.clip(foreground,0,1)*255)));front.save(P/(side+'Foreground.png'))
 c['closed_bounds']=[float(u[0,0]-6),float(min(u[:,1])-6),float(u[-1,0]+6),float(max(l[:,1])+6)]
(P/'eyes.json').write_text(json.dumps(configs,indent=2))
