/* VELQIO Unterschriftsseite (Kundenhandy oder Werkstatt-Tablet).
   Zeigt genau die Angaben, die der Kunde bestätigt, lässt ihn lesen, bestätigen und unterschreiben.
   Transport wird von außen übergeben: load() und submit(signature, payloadVersion). */
const VelqioSignPage=(function(){
  const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const STYLE=`
  .vsp{--g:#1f8a4c;--ink:#1f2b25;--muted:#5d6e64;--line:#e1e8e3;min-height:100dvh;margin:0;background:#f4f7f5;color:var(--ink);font:16px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;padding:env(safe-area-inset-top,0) 0 env(safe-area-inset-bottom,0)}
  .vsp *{box-sizing:border-box}
  .vsp-wrap{max-width:640px;margin:0 auto;padding:18px 16px 28px}
  .vsp-shop{font-size:13px;font-weight:600;color:var(--muted);margin:0 0 2px}
  .vsp h1{font-size:22px;line-height:1.25;margin:0 0 14px}
  .vsp-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 12px}
  .vsp-facts{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0}
  .vsp-facts dt{color:var(--muted);font-size:14px}.vsp-facts dd{margin:0;font-weight:600;overflow-wrap:anywhere}
  .vsp h2{font-size:14px;margin:0 0 8px;color:var(--muted);font-weight:600}
  .vsp-checks{list-style:none;margin:0;padding:0;display:grid;gap:6px}
  .vsp-checks li{display:flex;gap:8px;align-items:flex-start;font-size:15px}.vsp-checks li:before{content:'✓';color:var(--g);font-weight:700}
  .vsp-note{margin:0;padding:10px 12px;border-left:3px solid #c0720f;background:#fdf6ea;border-radius:0 8px 8px 0;font-size:15px}
  .vsp-confirm{font-size:15.5px;margin:0}
  .vsp-agree{display:flex;gap:10px;align-items:flex-start;margin:4px 0 12px;font-size:15px;font-weight:600}
  .vsp-agree input{width:22px;height:22px;flex:0 0 22px;accent-color:var(--g);margin:1px 0 0}
  .vsp-pad{position:relative;background:#fff;border:2px dashed #b9cfc2;border-radius:12px;touch-action:none}
  .vsp-pad canvas{display:block;width:100%;height:190px;touch-action:none}
  .vsp-pad span{position:absolute;left:14px;bottom:10px;font-size:13px;color:#9aaba1;pointer-events:none}
  .vsp-actions{display:flex;gap:10px;margin-top:12px}
  .vsp-actions button{flex:1;height:50px;border-radius:10px;font-size:16px;font-weight:650;cursor:pointer}
  .vsp-clear{background:#fff;border:1px solid var(--line);color:var(--ink)}
  .vsp-send{background:var(--g);border:1px solid var(--g);color:#fff}
  .vsp-send:disabled{opacity:.5}
  .vsp-msg{margin:10px 0 0;font-size:14.5px;color:#8c2b2b}
  .vsp-done{text-align:center;padding:48px 16px}.vsp-done b{display:block;font-size:22px;margin-bottom:6px}
  .vsp-done i{display:grid;place-items:center;width:64px;height:64px;margin:0 auto 14px;border-radius:50%;background:#e4f4ea;color:var(--g);font-style:normal;font-size:32px}
  .vsp button:focus-visible,.vsp input:focus-visible{outline:3px solid #1f8a4c55;outline-offset:2px}`;
  function render(root,transport){
    const style=document.createElement('style');style.textContent=STYLE;document.head.appendChild(style);
    root.className='vsp';root.innerHTML='<div class="vsp-wrap"><p class="vsp-shop">Wird geladen …</p></div>';
    let version=0,dirty=false;
    const fail=m=>{root.innerHTML=`<div class="vsp-wrap"><div class="vsp-done"><i>!</i><b>Unterschrift nicht möglich</b><p>${esc(m)}</p></div></div>`;};
    function show(p,v){
      version=v;
      root.innerHTML=`<main class="vsp-wrap">
<p class="vsp-shop">${esc(p.workshop||'Werkstatt')}</p><h1>${esc(p.title)}</h1>
<section class="vsp-card"><dl class="vsp-facts">${p.facts.map(([a,b])=>`<dt>${esc(a)}</dt><dd>${esc(b)}</dd>`).join('')}</dl></section>
${p.checks&&p.checks.length?`<section class="vsp-card"><h2>${esc(p.checksTitle||'Gemeinsam erledigt')}</h2><ul class="vsp-checks">${p.checks.map(c=>`<li>${esc(c)}</li>`).join('')}</ul></section>`:''}
${p.note?`<section class="vsp-card"><h2>Vermerk</h2><p class="vsp-note">${esc(p.note)}</p></section>`:''}
<section class="vsp-card"><h2>Ihre Bestätigung</h2><p class="vsp-confirm">${esc(p.confirmText)}</p></section>
<label class="vsp-agree"><input type="checkbox" id="vsp-agree"> Ich habe die Angaben gelesen und bestätige sie.</label>
<div class="vsp-pad"><canvas id="vsp-canvas" aria-label="Hier mit dem Finger unterschreiben"></canvas><span>Hier unterschreiben</span></div>
<div class="vsp-actions"><button type="button" class="vsp-clear" id="vsp-clear">Löschen</button><button type="button" class="vsp-send" id="vsp-send">Unterschrift senden</button></div>
<p class="vsp-msg" id="vsp-msg" role="alert"></p></main>`;
      const c=root.querySelector('#vsp-canvas'),ctx=c.getContext&&c.getContext('2d');
      const size=()=>{if(!ctx)return;const r=c.getBoundingClientRect(),d=window.devicePixelRatio||1;c.width=Math.round(r.width*d);c.height=Math.round(r.height*d);ctx.setTransform(d,0,0,d,0,0);ctx.lineWidth=2.6;ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle='#15261d';dirty=false;};
      size();
      let drawing=false,last=null;
      const pos=e=>{const r=c.getBoundingClientRect(),t=e.touches?e.touches[0]:e;return {x:t.clientX-r.left,y:t.clientY-r.top};};
      c.addEventListener('pointerdown',e=>{drawing=true;last=pos(e);c.setPointerCapture&&c.setPointerCapture(e.pointerId);e.preventDefault();});
      c.addEventListener('pointermove',e=>{if(!drawing||!ctx)return;const p2=pos(e);ctx.beginPath();ctx.moveTo(last.x,last.y);ctx.lineTo(p2.x,p2.y);ctx.stroke();last=p2;dirty=true;});
      ['pointerup','pointercancel','pointerleave'].forEach(t=>c.addEventListener(t,()=>{drawing=false;}));
      root.querySelector('#vsp-clear').onclick=size;
      const msg=root.querySelector('#vsp-msg'),send=root.querySelector('#vsp-send');
      send.onclick=async()=>{
        msg.textContent='';
        if(!root.querySelector('#vsp-agree').checked){msg.textContent='Bitte bestätigen Sie, dass Sie die Angaben gelesen haben.';return;}
        if(!dirty){msg.textContent='Bitte unterschreiben Sie im Feld oben.';return;}
        send.disabled=true;send.textContent='Wird gesendet …';
        try{
          const out=document.createElement('canvas');out.width=720;out.height=240;const o=out.getContext('2d');o.drawImage(c,0,0,out.width,out.height);
          const result=await transport.submit(out.toDataURL('image/png'),version);
          if(result&&result.conflict){show(result.payload,result.payloadVersion);root.querySelector('#vsp-msg').textContent='Die Angaben wurden gerade in der Werkstatt geändert. Bitte noch einmal lesen, bestätigen und unterschreiben.';return;}
          root.innerHTML='<div class="vsp-wrap"><div class="vsp-done"><i>✓</i><b>Vielen Dank!</b><p>Ihre Unterschrift ist angekommen. Sie können dieses Fenster jetzt schließen.</p></div></div>';
        }catch(e){send.disabled=false;send.textContent='Unterschrift senden';msg.textContent=e.message||'Senden fehlgeschlagen. Bitte erneut versuchen.';}
      };
    }
    transport.load().then(r=>show(r.payload,r.payloadVersion)).catch(e=>fail(e.message||'Dieser Link ist ungültig.'));
  }
  /* Transport für den Server (Sites-Worker oder bestehende Installation mit gleicher Schnittstelle) */
  function serverTransport(token,base=''){
    const call=async body=>{const r=await fetch(base+'/api/public-sign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({token},body))});const d=await r.json().catch(()=>({}));return {r,d};};
    return {
      async load(){const {r,d}=await call({action:'get'});if(!r.ok)throw new Error(d.error||'Dieser Link ist ungültig.');return d;},
      async submit(signature,payloadVersion){const {r,d}=await call({action:'submit',signature,payloadVersion});if(r.status===409&&d.payload)return {conflict:true,payload:d.payload,payloadVersion:d.payloadVersion};if(!r.ok)throw new Error(d.error||'Senden fehlgeschlagen.');return d;}
    };
  }
  return {render,serverTransport};
})();
