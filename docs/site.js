// Repokase site: theme switching, copy buttons, the conveyor belt and the
// typed confirmation. No dependencies, nothing loaded from elsewhere.

const THEMES = {
  "ristretto": { shot: "screenshots/hero.png", color: "#2c2525" },
  "tokyo-night": { shot: "screenshots/theme-tokyo-night.png", color: "#1a1b26" },
  "catppuccin-latte": { shot: "screenshots/theme-latte.png", color: "#eff1f5" },
}
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches

// ── omarchy theme set ──────────────────────────────────────────────
function setTheme(name, save) {
  if (!THEMES[name]) name = "ristretto"
  document.documentElement.dataset.theme = name
  document.querySelector('meta[name="theme-color"]').content = THEMES[name].color
  for (const b of document.querySelectorAll("[data-set-theme]")) {
    b.setAttribute("aria-pressed", String(b.dataset.setTheme === name))
  }
  const hero = document.getElementById("hero-img")
  const shot = THEMES[name].shot
  if (hero && !hero.src.endsWith(shot)) {
    if (reducedMotion) {
      hero.src = shot
    } else {
      hero.classList.add("swapping")
      const next = new Image()
      next.onload = () => { hero.src = shot; hero.classList.remove("swapping") }
      next.src = shot
    }
  }
  if (save) {
    try { localStorage.setItem("repokase-theme", name) } catch (e) {}
  }
}

for (const b of document.querySelectorAll("[data-set-theme]")) {
  b.addEventListener("click", () => setTheme(b.dataset.setTheme, true))
}
setTheme(document.documentElement.dataset.theme, false)

// ── copy buttons ───────────────────────────────────────────────────
for (const b of document.querySelectorAll("[data-copy]")) {
  b.addEventListener("click", async () => {
    const text = document.querySelector(b.dataset.copy).textContent.trim()
    try {
      await navigator.clipboard.writeText(text)
      b.textContent = "Copied"
    } catch (e) {
      b.textContent = "Select & copy"
    }
    setTimeout(() => { b.textContent = "Copy" }, 1600)
  })
}

// ── kaiten: duplicate the plates so the loop is seamless ───────────
const plates = document.querySelector("[data-plates]")
if (plates && !reducedMotion) {
  for (const li of [...plates.children]) {
    const copy = li.cloneNode(true)
    copy.setAttribute("aria-hidden", "true")
    plates.appendChild(copy)
  }
}

// ── mukozuke: type the name, then the danger button arms ──────────
const field = document.querySelector(".typing")
if (field) {
  const cut = field.closest(".cut")
  const target = field.dataset.type
  const type = () => {
    if (reducedMotion) { field.textContent = target; cut.classList.add("armed"); return }
    let i = 0
    field.textContent = ""
    cut.classList.remove("armed")
    const tick = () => {
      field.textContent = target.slice(0, ++i)
      if (i < target.length) setTimeout(tick, 55 + Math.random() * 70)
      else cut.classList.add("armed")
    }
    tick()
  }
  if (reducedMotion || !("IntersectionObserver" in window)) type()
  else new IntersectionObserver((entries, obs) => {
    if (entries.some((e) => e.isIntersecting)) { type(); obs.disconnect() }
  }, { threshold: 0.6 }).observe(cut)
}
