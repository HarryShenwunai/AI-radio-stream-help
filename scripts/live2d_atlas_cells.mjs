// Texture extraction contracts only; these helpers never paint image pixels.
function boundaries(size,count,explicit){
 if(!Number.isInteger(size)||size<=0||!Number.isInteger(count)||count<=0)throw new Error('Invalid atlas dimensions.');
 const values=explicit??Array.from({length:count+1},(_,i)=>Math.floor(i*size/count));
 if(!Array.isArray(values)||values.length!==count+1||values[0]!==0||values.at(-1)!==size||values.some((v,i)=>!Number.isInteger(v)||(i&&v<=values[i-1])))throw new Error('Atlas boundaries must cover the image with increasing integer coordinates.');
 return values;
}
export function atlasCell({width,height,col,row,cols,rows,xBounds,yBounds}){
 const xs=boundaries(width,cols,xBounds),ys=boundaries(height,rows,yBounds);
 if(!Number.isInteger(col)||!Number.isInteger(row)||col<0||col>=cols||row<0||row>=rows)throw new Error('Atlas cell index is outside the image.');
 return {left:xs[col],top:ys[row],width:xs[col+1]-xs[col],height:ys[row+1]-ys[row]};
}
export function assertTransparentCellEdges(data,info,label,{threshold=8}={}){
 const {width,height,channels}=info;
 if(!Number.isInteger(width)||!Number.isInteger(height)||width<2||height<2||channels!==4||data.length!==width*height*4||!Number.isInteger(threshold)||threshold<1||threshold>255)throw new Error('RGBA atlas cell and a bounded alpha threshold are required.');
 const edges={top:0,bottom:0,left:0,right:0};
 for(let x=0;x<width;x++){if(data[x*4+3]>=threshold)edges.top++;if(data[((height-1)*width+x)*4+3]>=threshold)edges.bottom++;}
 for(let y=0;y<height;y++){if(data[y*width*4+3]>=threshold)edges.left++;if(data[(y*width+width-1)*4+3]>=threshold)edges.right++;}
 if(Object.values(edges).some(Boolean))throw new Error('Atlas cell cuts visible artwork: '+label+' '+JSON.stringify(edges)+'. Select actual transparent gutters; do not assume evenly spaced rows.');
 return {alpha_threshold:threshold,visible_boundary_pixels:edges};
}
