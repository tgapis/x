function cp(t){var c=document.getElementById("c");c.value=t;c.select();try{document.execCommand("copy")}catch(e){}}
/* Python syntax highlighter */
function hlPy(t){
  var K='import|from|as|async|def|await|return|class|if|elif|else|for|in|not|and|or|None|True|False|pass|with|try|except|raise|yield|lambda'.split('|');
  function e(s){return s.replace(/&/g,'&amp;').replace(/\x3c/g,'&lt;').replace(/\x3e/g,'&gt;');}
  var o='',i=0,n=t.length;
  while(i<n){
    var c=t[i];
    if(c==='#'){var j=t.indexOf('\n',i);j=j<0?n:j;o+='<span class="py-c">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    if(c==='"'||c==="'"){var q=c,j=i+1;while(j<n&&t[j]!==q){if(t[j]==='\\')j++;j++;}j++;o+='<span class="py-s">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    if(/[a-zA-Z_]/.test(c)){var j=i;while(j<n&&/[a-zA-Z0-9_]/.test(t[j]))j++;var w=t.slice(i,j);o+=K.indexOf(w)>=0?'<span class="py-k">'+w+'</span>':e(w);i=j;continue;}
    if(/[0-9]/.test(c)&&(i===0||!/[a-zA-Z_]/.test(t[i-1]))){var j=i;while(j<n&&/[0-9a-fA-FxXbBoO._]/.test(t[j]))j++;o+='<span class="py-n">'+t.slice(i,j)+'</span>';i=j;continue;}
    o+=e(c);i++;
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
    document.querySelectorAll('pre.python').forEach(function(p){p.innerHTML=hlPy(p.textContent);});
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