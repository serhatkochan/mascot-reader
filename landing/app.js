'use strict';

(() => {
  const mascots = {
    ember: {name: 'Kıvılcım', type: 'turuncu robot'},
    frost: {name: 'Buzkuşu', type: 'mavi baykuş'},
    fern: {name: 'Yaprak', type: 'yeşil tilki'},
    neko: {name: 'Mırmır', type: 'alacalı kedi'},
    cloud: {name: 'Bulut', type: 'lavanta hayalet'},
    cosmo: {name: 'Kozmo', type: 'mor astronot'},
    panda: {name: 'Panda', type: 'kulaklıklı panda'},
    axolotl: {name: 'Nori', type: 'pembe aksolotl'},
    dragon: {name: 'Luna', type: 'turkuaz ejderha'},
    raccoon: {name: 'Piko', type: 'gri rakun'},
  };
  const options = [...document.querySelectorAll('[data-mascot]')];
  const portrait = document.getElementById('mascot-portrait');
  const still = document.getElementById('mascot-still');
  const selection = document.getElementById('mascot-selection');

  function selectMascot(button) {
    const id = button.dataset.mascot;
    const mascot = mascots[id];
    if (!mascot) return;
    options.forEach(option => {
      const selected = option === button;
      option.setAttribute('aria-checked', String(selected));
      option.tabIndex = selected ? 0 : -1;
    });
    still.srcset = `assets/mascots/${id}.png`;
    portrait.src = `assets/mascots/${id}.${id === 'ember' ? 'gif' : 'png'}`;
    portrait.alt = `Dizüstü bilgisayarının başındaki ${mascot.type} ${mascot.name}`;
    selection.textContent = `${mascot.name} seçildi.`;
  }

  options.forEach((button, index) => {
    button.addEventListener('click', () => selectMascot(button));
    button.addEventListener('keydown', event => {
      const offsets = {ArrowRight: 1, ArrowLeft: -1, ArrowDown: 5, ArrowUp: -5};
      let next;
      if (Object.hasOwn(offsets, event.key)) next = (index + offsets[event.key] + options.length) % options.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = options.length - 1;
      else return;
      event.preventDefault();
      selectMascot(options[next]);
      options[next].focus();
    });
  });

  const seek = document.getElementById('preview-seek');
  const time = document.getElementById('preview-time');
  const play = document.getElementById('preview-play');
  const icon = document.getElementById('play-icon');
  const back = document.getElementById('preview-back');
  const forward = document.getElementById('preview-forward');
  const skipButtons = [...document.querySelectorAll('[data-skip]')];
  const duration = Number(seek.max);
  let position = Number(seek.value);
  let playing = false;
  let skip = 10;
  let timer = null;
  let previousTick = 0;
  let scrubbing = false;

  function updatePosition(value) {
    position = Math.min(duration, Math.max(0, value));
    const seconds = Math.floor(position);
    seek.value = String(seconds);
    seek.style.setProperty('--progress', `${position / duration * 100}%`);
    seek.setAttribute('aria-valuetext', `${seconds} saniye / 2 dakika 40 saniye`);
    time.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    if (position >= duration && playing && !scrubbing) setPlaying(false);
  }

  function setPlaying(value) {
    playing = value;
    play.setAttribute('aria-pressed', String(value));
    play.setAttribute('aria-label', value ? 'Önizlemeyi duraklat' : 'Önizlemeyi oynat');
    icon.setAttribute('href', value ? '#icon-pause' : '#icon-play');
    if (timer !== null) clearInterval(timer);
    timer = null;
    if (value) {
      previousTick = performance.now();
      timer = setInterval(() => {
        const now = performance.now();
        const elapsed = (now - previousTick) / 1000;
        previousTick = now;
        if (!scrubbing && !document.hidden) updatePosition(position + elapsed);
      }, 150);
    }
  }

  play.addEventListener('click', () => {
    if (!playing && position >= duration) updatePosition(0);
    setPlaying(!playing);
  });
  document.getElementById('preview-restart').addEventListener('click', () => {
    updatePosition(0);
    setPlaying(true);
  });
  document.getElementById('preview-stop').addEventListener('click', () => {
    setPlaying(false);
    updatePosition(0);
  });
  back.addEventListener('click', () => updatePosition(position - skip));
  forward.addEventListener('click', () => updatePosition(position + skip));
  seek.addEventListener('input', () => updatePosition(Number(seek.value)));
  seek.addEventListener('pointerdown', () => { scrubbing = true; });
  const endScrub = () => {
    scrubbing = false;
    previousTick = performance.now();
    if (position >= duration && playing) setPlaying(false);
  };
  window.addEventListener('pointerup', endScrub);
  window.addEventListener('pointercancel', endScrub);
  seek.addEventListener('blur', endScrub);

  skipButtons.forEach(button => button.addEventListener('click', () => {
    skip = Number(button.dataset.skip);
    skipButtons.forEach(option => option.setAttribute('aria-pressed', String(option === button)));
    document.getElementById('back-label').textContent = `−${skip}`;
    document.getElementById('forward-label').textContent = `+${skip}`;
    back.setAttribute('aria-label', `Önizlemede ${skip} saniye geri`);
    forward.setAttribute('aria-label', `Önizlemede ${skip} saniye ileri`);
  }));

  document.addEventListener('visibilitychange', () => { previousTick = performance.now(); });
  window.addEventListener('pagehide', () => setPlaying(false));
  updatePosition(position);
})();
