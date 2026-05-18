function cp(t){var c=document.getElementById("c");c.value=t;c.select();try{document.execCommand("copy")}catch(e){}}
function hlRs(t){
  var K='use|pub|async|fn|await|let|mut|struct|enum|impl|trait|type|const|static|if|else|match|for|in|loop|while|return|true|false|self|Self|super|crate|mod|where|as|move|ref|unsafe|Ok|Err|Some|None|Box|Vec|Option|Result|String|tokio|main|anyhow'.split('|');
  function e(s){return s.replace(/&/g,'&amp;').replace(/\x3c/g,'&lt;').replace(/\x3e/g,'&gt;');}
  var o='',i=0,n=t.length;
  while(i<n){
    var c2=t[i];
    // line comment
    if(c2==='/'&&t[i+1]==='/'){var j=t.indexOf('\n',i);j=j<0?n:j;o+='<span class="rs-cmt">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    // block comment
    if(c2==='/'&&t[i+1]==='*'){var j=t.indexOf('*/',i+2);j=j<0?n:j+2;o+='<span class="rs-cmt">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    // string
    if(c2==='"'){var j=i+1;while(j<n&&t[j]!=='"'){if(t[j]==='\\')j++;j++;}j++;o+='<span class="rs-str">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    // macro call (word followed by !)
    if(/[a-zA-Z_]/.test(c2)){var j=i;while(j<n&&/[a-zA-Z0-9_]/.test(t[j]))j++;var w=t.slice(i,j);
      if(t[j]==='!'){o+='<span class="rs-mac">'+e(w)+'!</span>';i=j+1;continue;}
      o+=K.indexOf(w)>=0?'<span class="rs-kw">'+w+'</span>':e(w);i=j;continue;}
    // number (including type suffixes like 0_i32)
    if(/[0-9]/.test(c2)&&(i===0||!/[a-zA-Z_]/.test(t[i-1]))){var j=i;while(j<n&&/[0-9a-fA-FxXbBoO._]/.test(t[j]))j++;
      if(/[iuf]/.test(t[j])){while(j<n&&/[a-z0-9]/.test(t[j]))j++;}
      o+='<span class="rs-num">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    o+=e(c2);i++;
  }
  return o;
}
function toast(){
  var d=document.createElement('div');
  d.textContent='Copied!';
  d.style.cssText='position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;padding:6px 16px;border-radius:20px;font-size:13px;font-family:monospace;z-index:9999;pointer-events:none;opacity:1;transition:opacity .4s';
  document.body.appendChild(d);
  setTimeout(function(){d.style.opacity='0';setTimeout(function(){d.remove();},400);},1200);
}
(function(){
  function attachLongPress(el){
    var _lpt=null;
    el.addEventListener('touchstart',function(){
      _lpt=setTimeout(function(){cp(el.innerText||el.textContent);toast();},600);
    },{passive:true});
    el.addEventListener('touchend',function(){clearTimeout(_lpt);});
    el.addEventListener('touchmove',function(){clearTimeout(_lpt);});
  }
  function addCopyIcon(pre){
    var code=(pre.textContent||pre.innerText).replace(/\n$/,'');
    var btn=document.createElement('button');
    btn.className='copy-icon';btn.textContent='copy';
    btn.addEventListener('click',function(ev){
      ev.stopPropagation();
      cp(code);
      btn.textContent='\u2713';toast();
      setTimeout(function(){btn.textContent='copy';},1300);
    });
    pre.appendChild(btn);
  }
  function init(){
    document.querySelectorAll('pre.rust').forEach(function(p){p.innerHTML=hlRs(p.textContent);});
    document.querySelectorAll('pre').forEach(function(el){addCopyIcon(el);attachLongPress(el);});
    document.querySelectorAll('.tabs .tab').forEach(function(btn,i){
      btn.addEventListener('touchend',function(e){e.preventDefault();switchWayTab(i);});
    });
  }
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',init);}else{init();}
})();
function switchWayTab(n){
  document.querySelectorAll('.tabs .tab').forEach(function(t,i){t.classList.toggle('active',i===n);});
  document.querySelectorAll('.way-content').forEach(function(c,i){c.classList.toggle('active',i===n);});
}