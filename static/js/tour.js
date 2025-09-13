(function () {
  const KEY = "sr_tour_seen_v1";

  function byStep(n){ return document.querySelector(`[data-tour-step="${n}"]`); }
  function steps(){ return [...document.querySelectorAll("[data-tour-step]")].sort((a,b)=>+a.dataset.tourStep-+b.dataset.tourStep); }

  function startTour(){ if(!steps().length) return;
    let i = 0;
    const overlay = document.createElement("div"); overlay.className="tour-overlay";
    const highlight = document.createElement("div"); highlight.className="tour-highlight";
    const pop = document.createElement("div"); pop.className="tour-pop";
    const text = document.createElement("div"); text.className="tour-text";
    const actions = document.createElement("div"); actions.className="tour-actions";
    const prevBtn = btn("Back"), nextBtn = btn("Next"), doneBtn = btn("Finish","primary");

    actions.append(prevBtn,nextBtn,doneBtn); pop.append(text,actions);
    document.body.append(overlay,highlight,pop);

    overlay.style.display = "block"; doneBtn.style.display="none"; prevBtn.disabled=true;

    function btn(label,variant){ const b=document.createElement("button");
      b.type="button"; b.className=`btn btn-${variant||"light"} btn-sm`; b.textContent=label; return b; }

    function place(){
      const el = steps()[i]; if(!el) return end();
      const r = el.getBoundingClientRect(), pad=8;
      Object.assign(highlight.style,{
        left: (window.scrollX+r.left - pad)+"px",
        top: (window.scrollY+r.top - pad)+"px",
        width: (r.width + pad*2)+"px",
        height: (r.height + pad*2)+"px"
      });
      const popX = window.scrollX+r.left + Math.min(300, Math.max(0, r.width-300)/2);
      const popY = window.scrollY+r.bottom + 10;
      Object.assign(pop.style,{ left: popX+"px", top: popY+"px" });
      text.textContent = el.dataset.tourText || "";
      prevBtn.disabled = i===0;
      nextBtn.style.display = i===steps().length-1 ? "none" : "";
      doneBtn.style.display = i===steps().length-1 ? "" : "none";
      el.scrollIntoView({behavior:"smooth", block:"center"});
    }

    function end(){ overlay.remove(); highlight.remove(); pop.remove(); localStorage.setItem(KEY,"1"); }

    nextBtn.onclick = ()=>{ i=Math.min(i+1, steps().length-1); place(); };
    prevBtn.onclick = ()=>{ i=Math.max(i-1, 0); place(); };
    doneBtn.onclick = end;
    overlay.onclick = end;

    place();
  }

  document.addEventListener("DOMContentLoaded", function(){
    // Only auto-run on pages that opt-in
    const wantsTour = document.body.hasAttribute("data-enable-tour");
    if (wantsTour && !localStorage.getItem(KEY)) startTour();

    // Optional: expose a global to re-run from a help link
    window.SR_TOUR_START = startTour;
  });
})();
