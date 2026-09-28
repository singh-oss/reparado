/* VELQIO Foto-Seite (Handy oder Tablet): Kamera öffnen, Fotos werden verkleinert und sofort übertragen. */
const VelqioPhotoPage=(function(){
  const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const STYLE=`
  .vpp{--g:#1f8a4c;--ink:#1f2b25;--muted:#5d6e64;--line:#e1e8e3;min-height:100dvh;margin:0;background:#f4f7f5;color:var(--ink);font:16px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif}
  .vpp *{box-sizing:border-box}
  .vpp-wrap{max-width:560px;margin:0 auto;padding:18px 16px 28px}
  .vpp-shop{font-size:13px;font-weight:600;color:var(--muted);margin:0 0 2px}
  .vpp h1{font-size:22px;line-height:1.25;margin:0 0 6px}
  .vpp p{margin:0 0 14px;color:var(--muted);font-size:15px}
  .vpp-shoot{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;height:64px;border:0;border-radius:14px;background:var(--g);color:#fff;font-size:18px;font-weight:650;cursor:pointer}
  .vpp-shoot input{display:none}
  .vpp-status{margin:14px 0 8px;font-size:15px;font-weight:600}
  .vpp-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
  .vpp-grid figure{margin:0;position:relative;aspect-ratio:1;border-radius:10px;overflow:hidden;background:#e3e9e5}
  .vpp-grid img{width:100%;height:100%;object-fit:cover;display:block}
  .vpp-grid figcaption{position:absolute;inset:auto 0 0 0;padding:2px 6px;font-size:11px;background:#000a;color:#fff}
  .vpp-grid .is-error figcaption{background:#b42318}
  .vpp-msg{margin-top:10px;color:#8c2b2b;font-size:14.5px}
  .vpp-done{display:block;width:100%;height:50px;margin-top:16px;border:1px solid var(--line);border-radius:12px;background:#fff;font-size:16px;font-weight:600;color:var(--ink);cursor:pointer}
  .vpp-end{text-align:center;padding:48px 16px}.vpp-end b{display:block;font-size:22px;margin-bottom:6px}
  .vpp-end i{display:grid;place-items:center;width:64px;height:64px;margin:0 auto 14px;border-radius:50%;background:#e4f4ea;color:var(--g);font-style:normal;font-size:32px}`;
  function shrink(file,max=1600,quality=0.82){
    return new Promise((resolve,reject)=>{
      const img=new Image(),url=URL.createObjectURL(file);
      img.onload=()=>{const r=Math.min(1,max/Math.max(img.width,img.height)),c=document.createElement('canvas');c.width=Math.round(img.width*r);c.height=Math.round(img.height*r);c.getContext('2d').drawImage(img,0,0,c.width,c.height);URL.revokeObjectURL(url);resolve(c.toDataURL('image/jpeg',quality));};
      img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('Dieses Foto konnte nicht gelesen werden.'));};
      img.src=url;
    });
  }
  function render(root,transport,opts={}){
    const style=document.createElement('style');style.textContent=STYLE;document.head.appendChild(style);
    root.className='vpp';root.innerHTML='<div class="vpp-wrap"><p class="vpp-shop">Wird geladen …</p></div>';
    let count=0,max=20;
    const end=(icon,title,text)=>{root.innerHTML=`<div class="vpp-wrap"><div class="vpp-end"><i>${icon}</i><b>${esc(title)}</b><p>${esc(text)}</p></div></div>`;};
    transport.load().then(info=>{
      count=info.count||0;max=info.max||20;
      root.innerHTML=`<main class="vpp-wrap"><p class="vpp-shop">${esc(opts.workshop||'Werkstatt')}</p><h1>Fotos für ${esc(info.title)}</h1>
<p>Gerät von allen Seiten fotografieren, besonders Display, Rückseite, Kanten und vorhandene Schäden. Die Fotos erscheinen sofort in der Werkstatt.</p>
<label class="vpp-shoot"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3.5"/></svg>Foto aufnehmen<input type="file" accept="image/*" capture="environment" multiple id="vpp-input"></label>
<p class="vpp-status" id="vpp-status" role="status">${count?count+' Foto'+(count>1?'s':'')+' übertragen':'Noch keine Fotos'}</p>
<div class="vpp-grid" id="vpp-grid"></div><p class="vpp-msg" id="vpp-msg" role="alert"></p>
<button type="button" class="vpp-done" id="vpp-done">Fertig</button></main>`;
      const grid=root.querySelector('#vpp-grid'),status=root.querySelector('#vpp-status'),msg=root.querySelector('#vpp-msg');
      root.querySelector('#vpp-done').onclick=()=>{if(opts.onDone)opts.onDone();end('✓','Danke!',count+' Foto'+(count===1?'':'s')+' übertragen. Sie können dieses Fenster schließen.');};
      root.querySelector('#vpp-input').onchange=async e=>{
        msg.textContent='';
        for(const file of Array.from(e.target.files||[])){
          if(count>=max){msg.textContent='Es können höchstens '+max+' Fotos übertragen werden.';break;}
          const fig=document.createElement('figure');fig.innerHTML='<figcaption>wird übertragen …</figcaption>';grid.prepend(fig);
          try{const data=await shrink(file);fig.insertAdjacentHTML('afterbegin',`<img src="${data}" alt="">`);const r=await transport.upload(data);count=r.count||count+1;fig.querySelector('figcaption').textContent='✓ übertragen';status.textContent=count+' Foto'+(count>1?'s':'')+' übertragen';}
          catch(err){fig.classList.add('is-error');fig.querySelector('figcaption').textContent='nicht übertragen';msg.textContent=err.message||'Übertragung fehlgeschlagen. Bitte erneut versuchen.';}
        }
        e.target.value='';
      };
    }).catch(e=>end('!','Fotos nicht möglich',e.message||'Dieser Link ist ungültig.'));
  }
  function serverTransport(token,base=''){
    const call=async body=>{const r=await fetch(base+'/api/public-photo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({token},body))});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'Übertragung fehlgeschlagen.');return d;};
    return {load:()=>call({action:'get'}),upload:image=>call({action:'upload',image})};
  }
  return {render,serverTransport,shrink};
})();
