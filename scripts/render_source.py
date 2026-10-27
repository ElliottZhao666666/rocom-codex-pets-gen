"""Render standard-directory source animation poses with a compatible local renderer.
No asset acquisition or archive parsing is included.
"""
from pathlib import Path
import sys, json, tomllib, struct, math, bisect, copy, shutil, subprocess, hashlib
from PIL import Image, ImageDraw, ImageFont
sys.stdout.reconfigure(encoding='utf-8')
from validate_input import validate_input, read_glb, require
from color_appearance import resolve_appearance, ChoiceRequired

def toml_value(value):
 if isinstance(value,bool):return 'true' if value else 'false'
 if isinstance(value,str):return json.dumps(value,ensure_ascii=False)
 if isinstance(value,dict):return '{'+', '.join(toml_key(k)+' = '+toml_value(v) for k,v in value.items())+'}'
 if isinstance(value,list):return '['+', '.join(toml_value(v) for v in value)+']'
 return repr(value)
def toml_key(k):return k if __import__('re').fullmatch(r'[A-Za-z0-9_-]+',k) else json.dumps(k,ensure_ascii=False)
def single_manifest(original,form,appearance):
 result={k:copy.deepcopy(v) for k,v in original.items() if k not in ('species','forms')}
 result['species']={'id':form['id'],'name':form['name'],'chain':[form['id']]};result['forms']=[form]
 lines=[toml_key(k)+' = '+toml_value(v) for k,v in result.items() if k not in ('species','forms')]
 lines+=['[species]']+[toml_key(k)+' = '+toml_value(v) for k,v in result['species'].items()]
 lines+=['[[forms]]']+[toml_key(k)+' = '+toml_value(v) for k,v in form.items()]
 text='\n'.join(lines)+'\n';require(tomllib.loads(text)==result,'Manifest serialization mismatch');return text

def initialize(input_dir,output_dir,renderer,rig,appearance_choice=None):
 global SOURCE,RUN,EXE,MAN,FORM,DOC,BIN,NODES,PARENTS,ANIMS,GAZE_RIG,ROOT_NODE,GAZE_YAW,GAZE_PITCH,APPEARANCE
 _,entity,MAN=validate_input(input_dir)
 SOURCE=Path(input_dir).resolve();RUN=Path(output_dir).resolve();EXE=Path(renderer).resolve()
 require(not RUN.is_relative_to(SOURCE),'Output must be outside input')
 require(EXE.is_file(),'A compatible renderer executable is required')
 FORM=MAN['forms'][0]
 APPEARANCE=resolve_appearance(SOURCE,entity,FORM,appearance_choice)
 for record_name in ('appearance-selection.json','render-provenance.json'):
  path=RUN/record_name
  if path.is_file():
   previous=json.loads(path.read_text(encoding='utf-8-sig'))
   previous=previous.get('appearance',previous)
   require(previous.get('identity')==entity['identity'],'Output already belongs to another entity/form/palette')
   if 'variant_key' in previous:require(previous['variant_key']==APPEARANCE['variant_key'],'Output already belongs to another color effect; choose a separate output directory')
   else:require(APPEARANCE['effect']=='none','Legacy base-color output cannot be reused for a color effect')
 RUN.mkdir(parents=True,exist_ok=True)
 (RUN/'appearance-selection.json').write_text(json.dumps(APPEARANCE,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 DOC,BIN=read_glb(SOURCE/'model.glb');NODES=DOC['nodes']
 PARENTS={c:i for i,n in enumerate(NODES) for c in n.get('children',[])}
 ROOT_NODE=rig.get('root_node')
 GAZE_RIG=rig.get('gaze_nodes',[])
 GAZE_YAW=rig.get('gaze_yaw_degrees',32)
 GAZE_PITCH=rig.get('gaze_pitch_degrees',29)
 require(all(type(v) in (int,float) and math.isfinite(v) and 0<v<=45 for v in (GAZE_YAW,GAZE_PITCH)),'Gaze amplitudes must be finite and within (0,45] degrees')
 for entry in GAZE_RIG:
  require(type(entry['node']) is int and 0<=entry['node']<len(NODES),'Invalid gaze bone index')
 require(all(e.get('weight',0)>=0 for e in GAZE_RIG),'Invalid gaze bone weight')
 require(not GAZE_RIG or abs(sum(e['weight'] for e in GAZE_RIG)-1)<.00001,'Gaze bone weights must sum to one')
 ANIMS=load_animations()

def qmul(a,b):
 x,y,z,w=a;X,Y,Z,W=b
 return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def inv(q):return [-q[0],-q[1],-q[2],q[3]]
def norm(q):
 d=math.sqrt(sum(x*x for x in q));return [x/d for x in q]
def slerp(a,b,t):
 d=sum(x*y for x,y in zip(a,b))
 if d<0:b=[-x for x in b];d=-d
 if d>.9995:return norm([x+(y-x)*t for x,y in zip(a,b)])
 an=math.acos(min(1,d));s=math.sin(an)
 return [(math.sin((1-t)*an)*x+math.sin(t*an)*y)/s for x,y in zip(a,b)]
def axis(a,rad):
 q=[0.,0.,0.,math.cos(rad/2)];q[a]=math.sin(rad/2);return q
def accessor(i):
 a=DOC['accessors'][i];v=DOC['bufferViews'][a['bufferView']]
 n={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
 assert a['componentType']==5126
 return [list(struct.unpack_from('<'+'f'*n,BIN,v.get('byteOffset',0)+a.get('byteOffset',0)+j*v.get('byteStride',n*4))) for j in range(a['count'])]
def load_animations():
 result={}
 for a in DOC['animations']:
  tracks=[]
  for ch in a['channels']:
   sm=a['samplers'][ch['sampler']]
   require(sm.get('interpolation','LINEAR') in ('LINEAR','STEP'),'Cubic animation sampling is not supported')
   times=[v[0] for v in accessor(sm['input'])];values=accessor(sm['output'])
   if ch['target']['path']=='weights':
    flat=[x for v in values for x in v];require(len(flat)%len(times)==0,'Morph sampler shape mismatch')
    width=len(flat)//len(times);values=[flat[i:i+width] for i in range(0,len(flat),width)]
   tracks.append(dict(node=ch['target']['node'],path=ch['target']['path'],times=times,values=values,interp=sm.get('interpolation','LINEAR')))
  result[a['name']]=tracks
 return result
def pose(clip,seconds):
 p=[{k:copy.deepcopy(n.get(k,d)) for k,d in [('translation',[0,0,0]),('rotation',[0,0,0,1]),('scale',[1,1,1])]} for n in NODES]
 for t in ANIMS[clip]:
  ts=t['times'];j=max(0,min(len(ts)-1,bisect.bisect_right(ts,seconds)-1));k=min(j+1,len(ts)-1)
  f=0 if ts[k]==ts[j] or t['interp']=='STEP' else max(0,min(1,(seconds-ts[j])/(ts[k]-ts[j])))
  p[t['node']][t['path']]=slerp(t['values'][j],t['values'][k],f) if t['path']=='rotation' else [a+(b-a)*f for a,b in zip(t['values'][j],t['values'][k])]
 return p
def worldrot(p,i):
 return qmul(worldrot(p,PARENTS[i]),p[i]['rotation']) if i in PARENTS else p[i]['rotation']
def gaze(p,deg):
 # Local rig posing, with the feet/root held fixed. No image warp or new artwork.
 theta=math.radians(deg);yaw=math.radians(GAZE_YAW)*math.sin(theta);pitch=-math.radians(GAZE_PITCH)*math.cos(theta)
 require(GAZE_RIG,'Explicit verified gaze bone configuration is required')
 for entry in GAZE_RIG:
  n=entry['node'];weight=entry['weight']
  parent=worldrot(p,PARENTS[n]);delta=qmul(axis(1,yaw*weight),axis(0,pitch*weight))
  p[n]['rotation']=norm(qmul(qmul(qmul(inv(parent),delta),parent),p[n]['rotation']))
 return p
def face_at(clip,t):
 result={'eye':[[0,1],[1000,1]],'mouth':[[0,1],[1000,1]]}
 for channel,keys in FORM.get('face',{}).get(clip,{}).items():
  val=keys[0][1]
  for ms,value in keys:
   if ms>t*1000+.01:break
   val=value
  result[channel]=[[0,val],[1000,val]]
 return result
def snapshot(name,p):
 raw=name.encode();out=bytearray(struct.pack('<H',len(raw))+raw+struct.pack('<fHI',1.,1,2)+struct.pack('<ff',0.,1.))
 tracks=[(i,k,v) for i,n in enumerate(p) for k,v in n.items() if k in ('translation','rotation','scale')]
 out+=struct.pack('<I',len(tracks))
 for n,k,v in tracks:out+=struct.pack('<IBBH',n,{'translation':0,'rotation':1,'scale':2}[k],0,0)
 morphs=[n['weights'] for n in p if 'weights' in n]
 require(not morphs or all(m==morphs[0] for m in morphs),'Multiple incompatible morph channels are unsupported')
 out+=struct.pack('<BHBI',1,0,0,len(morphs[0])) if morphs else b'\0';words=[]
 for n,k,v in tracks:
  acc=0
  for val in v*2:
   word=(max(-32767,min(32767,round(val*32767)))&65535) if k=='rotation' else struct.unpack('<H',struct.pack('<e',val))[0]
   words.append((word-acc)&65535);acc=word
 if morphs:
  acc=0
  for value in morphs[0]*2:
   word=struct.unpack('<H',struct.pack('<e',value))[0];words.append((word-acc)&65535);acc=word
 out+=struct.pack('<I',len(words))+bytes(w&255 for w in words)+bytes(w>>8 for w in words)
 return bytes(out)
def bake(specs,tag,size=768,yaw=0):
 temp=RUN/'work/render'/tag
 temp.mkdir(parents=True,exist_ok=True)
 target=temp/'forms'/FORM['asset'];target.mkdir(parents=True,exist_ok=True)
 for item in (SOURCE/'forms'/FORM['asset']).rglob('*'):
  if item.is_file() and item.suffix in ['.png','.glb']:
   dest=target/item.relative_to(SOURCE/'forms'/FORM['asset']);dest.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(item,dest)
 f=copy.deepcopy(FORM);f['clips']={};f['face']={};f.pop('voice',None);f.pop('sfx',None)
 clips=[]
 for i,s in enumerate(specs):
  if APPEARANCE['effect']!='none':require('shader_time' in s,'Effect frames require explicit shader_time, separate from bone seconds')
  shader_time=s.get('shader_time',0)
  require(type(shader_time) in (int,float) and math.isfinite(shader_time) and shader_time>=0,'shader_time must be finite and nonnegative')
  s['shader_time']=shader_time
  name=s.get('render_name',f'P{i:03}');s['render_clip']=name
  logical=s['clip'];require(logical in FORM['clips'],'Unknown logical animation: '+logical)
  require(0<=s['seconds']<=FORM['clips'][logical]['ms']/1000+.002,'Animation sample is outside its duration')
  p=pose(FORM['clips'][logical]['clip'],s['seconds'])
  if s.get('lock_root_horizontal'):
   require(type(ROOT_NODE) is int and 0<=ROOT_NODE<len(NODES),'Explicit verified root_node is required')
   require(FORM['clips'][logical].get('root_motion_cm',0)>0,'Horizontal root lock requires declared locomotion root motion')
   anchor=pose(FORM['clips'][logical]['clip'],0)[ROOT_NODE]['translation']
   original=list(p[ROOT_NODE]['translation'])
   for component in (0,2):p[ROOT_NODE]['translation'][component]=anchor[component]
   s['root_motion_adjustment']={'node':ROOT_NODE,'original_translation':original,'in_place_translation':p[ROOT_NODE]['translation'],'vertical_motion_preserved':True}
  if 'gaze' in s:p=gaze(p,s['gaze'])
  if s.get('root_yaw'):
   require(type(ROOT_NODE) is int and 0<=ROOT_NODE<len(NODES),'Explicit verified root_node is required')
   p[ROOT_NODE]['rotation']=qmul(axis(1,math.radians(s['root_yaw'])),p[ROOT_NODE]['rotation'])
  clips.append(snapshot(name,p));f['clips'][name]={'clip':name,'ms':1000,'frames':2};f['face'][name]=s.get('face',face_at(s['clip'],s['seconds']))
 # Native loader expects an Idle clip. Alias the selected baseline snapshot.
 if 'Idle' not in f['clips']:
  clips.append(snapshot('Idle',pose(FORM['clips'].get('Idle',next(iter(FORM['clips'].values())))['clip'],0)));f['clips']['Idle']={'clip':'Idle','ms':1000,'frames':2}
 (target/'anim.rka').write_bytes(b'RKAN'+struct.pack('<BI',1,len(clips))+b''.join(clips))
 (temp/'manifest.toml').write_text(single_manifest(MAN,f,'normal'),encoding='utf-8')
 times=sorted(set(s['shader_time'] for s in specs));tiles=[None]*len(specs);phases=[]
 for phase,time in enumerate(times):
  name=tag if len(times)==1 else f'{tag}-phase-{phase:03}'
  output=RUN/'qa/native'/f'{name}.png';output.parent.mkdir(parents=True,exist_ok=True)
  # Every phase renders the complete identical pose family. Auto-fit therefore sees
  # the same geometry, instead of zooming/recentering each independently rendered pose.
  cmd=[str(EXE),'--render',str(temp),'--form',f['asset'],'--clips',','.join(s['render_clip'] for s in specs),'--at','0','--size',str(size),'--yaw',str(yaw),'--time',str(time),'--no-fade','--out',str(output)]
  if APPEARANCE['mutation']:cmd+=['--packs-dir',APPEARANCE['packs_directory'],'--mutation',APPEARANCE['mutation']]
  if output.exists():output.unlink()
  r=subprocess.run(cmd,capture_output=True,timeout=300,creationflags=0x08000000)
  indices=[i for i,s in enumerate(specs) if s['shader_time']==time]
  log={'tag':tag,'phase':phase,'shader_time':time,'command':cmd,'returncode':r.returncode,'log':(r.stdout+r.stderr).decode('utf-8','replace'),'selected_indices':indices,'specs':specs,'appearance':APPEARANCE,'shared_pose_family':True}
  (output.with_suffix('.json')).write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
  require(r.returncode==0 and output.exists(),'Renderer failed for selected appearance; no downgrade. See '+str(output.with_suffix('.json')))
  with Image.open(output) as opened:im=opened.convert('RGBA')
  require(im.size==(size*len(specs),size),'Unexpected rendered strip size')
  for i in indices:tiles[i]=im.crop((i*size,0,(i+1)*size,size))
  phases.append({'shader_time':time,'selected_indices':indices,'native_log':str(output.with_suffix('.json'))})
  print('RENDERED',tag,'phase',phase,'time',time,'family',len(specs),flush=True)
 require(all(tile is not None for tile in tiles),'Missing rendered phase frame')
 (RUN/'qa/native'/f'{tag}-phases.json').write_text(json.dumps({'phases':phases,'shared_pose_family':True},ensure_ascii=False,indent=2),encoding='utf-8')
 return tiles
def contact(frames,labels,path,cols=8):
 font=ImageFont.load_default(size=17);rows=math.ceil(len(frames)/cols)
 out=Image.new('RGB',(cols*192,rows*230),(223,227,234));d=ImageDraw.Draw(out)
 for i,(im,label) in enumerate(zip(frames,labels)):
  im=im.copy();im.thumbnail((192,208),Image.Resampling.LANCZOS);x=i%cols*192;y=i//cols*230
  out.paste(im,(x,y),im);d.text((x+4,y+210),label,font=font,fill='black')
 out.save(path)
def main():
 import argparse,platform
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
 parser.add_argument('--renderer',required=True);parser.add_argument('--plan',required=True)
 args=parser.parse_args();plan=json.loads(Path(args.plan).read_text(encoding='utf-8'))
 try:initialize(args.input,args.output,args.renderer,plan.get('rig',{}),plan.get('appearance'))
 except ChoiceRequired as exc:
  print(json.dumps({'ok':False,'status':'needs_input','questions':exc.questions},ensure_ascii=False,indent=2));raise SystemExit(2)
 specs=plan['frames'];require(specs and len(specs)<=128,'Plan must contain 1..128 frames')
 tag=plan.get('tag','source-render');require(__import__('re').fullmatch(r'[A-Za-z0-9_-]+',tag),'Invalid run tag')
 size=plan.get('size',1024);require(type(size) is int and 192<=size<=2048,'Native size must be 192..2048')
 tiles=bake(specs,tag,size,plan.get('camera_yaw',0))
 dest=RUN/'native-frames'/tag;dest.mkdir(parents=True,exist_ok=True)
 for index,frame in enumerate(tiles):frame.save(dest/f'{index:03}.png')
 records=[{'path':p.relative_to(SOURCE).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(SOURCE.rglob('*')) if p.is_file()]
 report={'input':str(SOURCE),'identity':json.loads((SOURCE/'entity.json').read_text(encoding='utf-8'))['identity'],'source_files':records,'renderer_sha256':hashlib.sha256(EXE.read_bytes()).hexdigest(),'python':platform.python_version(),'pillow':__import__('PIL').__version__,'frames':specs,'rig':plan.get('rig',{}),'appearance':APPEARANCE,'image_generation_used':False}
 (RUN/'render-provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Source rendered; final normalization, visual review and official Pets gates are still required.')

if __name__=='__main__':main()
