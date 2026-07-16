#!/usr/bin/env node
/*
 * docs/kahve.html DOM-stub testleri — jsdom'suz, saf node (vm modülü).
 *
 * Kapsam:
 *   1) Sözdizimi: sayfa script'i node --check ile doğrulanır.
 *   2) v3 fixture (tests/fixtures/kahve_v3_sample.json):
 *      - BUG FIX: 'sinyal yok' satırları varsayılan GİZLİ; görünen satır
 *        sayısı = sinyalli satır sayısı; toggle sayacı aynı koşulu sayar.
 *        (sutlac: mentions=0 ama prev/appearances>0 → yine gizli.)
 *      - Harita Genel karışımı: max(normalize(bahsetme), geo maks ilgi/100).
 *      - Kavram modu: yalnız o kavramın interest'i; chip metinleri.
 *      - Ülke kartı: 💬 Bahsetmeler + 📈 Google Trends ilgisi bölümleri.
 *      - Kapsam dürüstlüğü: coverage_gaps kesişim uyarısı, '⚠ kapsam' çipi,
 *        boş pencere probe açıklaması (daily/weekly) vs genel metin (monthly).
 *   3) Gerçek docs/data/kahve.json ile geriye-uyum (geo'suz → v2 davranışı).
 *
 * Çalıştırma:  node tests/test_kahve_dom.js
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');
const { execFileSync } = require('child_process');

const PKG = path.resolve(__dirname, '..');
const REPO = path.resolve(PKG, '..');
const HTML_PATH = path.join(REPO, 'docs', 'kahve.html');
const REAL_JSON = path.join(REPO, 'docs', 'data', 'kahve.json');
const FIXTURE = path.join(__dirname, 'fixtures', 'kahve_v3_sample.json');

let failures = 0;
function assert(cond, msg) {
  if (cond) { console.log('  ok - ' + msg); }
  else { failures++; console.error('  FAIL - ' + msg); }
}

function extractScript() {
  const html = fs.readFileSync(HTML_PATH, 'utf8');
  const m = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('kahve.html içinde <script> bulunamadı');
  return m[1];
}

// ── DOM stub ──────────────────────────────────────────────────────────────
function stubEl() {
  return {
    innerHTML: '', textContent: '', style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {}, appendChild() {},
    querySelector() { return null; },
    querySelectorAll() { return { forEach() {} }; },
  };
}

// Sayfa script'ini verilen kahve.json verisiyle çalıştır; sandbox döndür.
async function runPage(data) {
  const els = {};
  const sandbox = {
    document: {
      getElementById(id) { return els[id] || (els[id] = stubEl()); },
      querySelectorAll() { return { forEach() {} }; },
      addEventListener() {},
    },
    window: { innerWidth: 1200 },
    // Dış istek YOK sözleşmesi: yalnız ./data/kahve.json ve ./assets/world.svg
    // çağrılabilir. Başka URL görülürse test düşer.
    fetch: async (url) => {
      if (String(url).indexOf('./data/kahve.json') === 0) {
        return { ok: true, json: async () => data };
      }
      if (String(url) === './assets/world.svg') {
        return { ok: false, status: 404 }; // stub'da harita SVG'si yok
      }
      failures++;
      console.error('  FAIL - beklenmeyen fetch: ' + url);
      return { ok: false, status: 404 };
    },
    console: { log() {}, warn() {}, error() {} },
    requestAnimationFrame: (f) => f(),
    setTimeout,
    DOMParser: function () {
      this.parseFromString = () => ({
        querySelector: () => ({}),
        documentElement: { nodeName: 'div' },
      });
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(extractScript(), sandbox);
  await new Promise((r) => setTimeout(r, 20)); // async load() bitsin
  return {
    els,
    run: (code) => vm.runInContext(code, sandbox),
  };
}

function countRows(html) { return (html.match(/<tr class="(row|nosig)/g) || []).length; }
function countNosig(html) { return (html.match(/nosig-tag/g) || []).length; }

// ── 2) v3 fixture testleri ────────────────────────────────────────────────
async function testV3() {
  console.log('# v3 fixture');
  const data = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
  const page = await runPage(data);
  const { run, els } = page;

  // BUG FIX — weekly/tr: görünen satır sayısı = sinyalli satır sayısı
  run("win='weekly';grp='all';");
  let h = run("panelHtml('tr','TR','x')");
  const sigTr = data.items.filter((i) => i.metrics.weekly.tr.mentions > 0).length;
  assert(countRows(h) === sigTr, `weekly/tr görünen satır (${countRows(h)}) = sinyalli satır (${sigTr})`);
  assert(countNosig(h) === 0, "weekly/tr varsayılanda hiç 'sinyal yok' satırı yok");
  assert(h.indexOf('Sütlaç') === -1, 'sutlac (mentions=0, prev>0) varsayılanda gizli');
  assert(h.indexOf('Sinyalsiz 3 kavramı göster') !== -1, 'toggle sayacı = gizlenen satır sayısı (3)');

  // Toggle açınca: 3 nosig satırı görünür, sayaç 'gizle' olur
  run("showZero.tr=true;");
  h = run("panelHtml('tr','TR','x')");
  assert(countRows(h) === 4, 'toggle sonrası 4 satır (1 sinyal + 3 sinyalsiz)');
  assert(countNosig(h) === 3, "toggle sonrası 3 'sinyal yok' etiketi");
  assert(h.indexOf('Sütlaç') !== -1, 'sutlac toggle sonrası görünür');
  assert(h.indexOf('Sinyalsiz 3 kavramı gizle') !== -1, "toggle metni 'gizle' olur");
  run("showZero.tr=false;");

  // weekly/world: 2 sinyal (matcha, dubai)
  h = run("panelHtml('world','W','x')");
  assert(countRows(h) === 2 && countNosig(h) === 0, 'weekly/world görünen satır = 2 sinyalli, nosig yok');

  // esc() attribute bağlamında da güvenli
  assert(run("esc('<a b=\"c\">')") === '&lt;a b=&quot;c&quot;&gt;', 'esc() tırnakları da kaçırır');

  // Genel mod karışımı: max(normalize(bahsetme), geo maks ilgi/100)
  const vals = run('mapValues(mentionTotals())');
  assert(Math.abs(vals.JP - 0.95) < 1e-9, 'JP (yalnız geo, 95) → 0.95');
  assert(Math.abs(vals.US - 0.87) < 1e-9, 'US → geo 0.87 > bahsetme normalizasyonu');
  assert(Math.abs(vals.TR - 1) < 1e-9, 'TR (maks bahsetme) → 1.0');
  assert(vals.GB > 0 && vals.GB < 1, 'GB (yalnız bahsetme) log-normalize');
  assert(run('mapLegendText()') === 'bahsetme + Google Trends ilgisi (7g)', 'Genel legend dürüst');

  // Kavram modu: yalnız o kavramın interest/100
  run("MAP.concept='matcha';");
  const cvals = run('mapValues(mentionTotals())');
  assert(Math.abs(cvals.JP - 0.95) < 1e-9 && Math.abs(cvals.TR - 0.41) < 1e-9, 'kavram modu: interest/100');
  assert(!('GB' in cvals), 'kavram modunda bahsetme ülkesi (GB) boyanmaz');
  assert(run('mapLegendText()') === 'Google Trends ilgisi 0-100 (son 7 gün)', 'kavram modu legend');
  let chip = run('mapChipHtml()');
  assert(chip.indexOf('🗺 Matcha — Google Trends ilgisi (son 7 gün)') !== -1, 'kavram çipi metni');
  assert(chip.indexOf('× Genel görünüme dön') !== -1, 'çipte Genel dönüş düğmesi');
  run('mapGeneral();');
  assert(run('mapChipHtml()') === '' && run('MAP.concept') === null, 'mapGeneral() Genel moda döner');

  // Satır tıklama akışı: geo'lu kavram → kavram modu; geo'suz → uyarı çipi
  run("toggleRow('tr','matcha');");
  assert(run('MAP.concept') === 'matcha', 'detay açılınca harita kavram moduna geçer');
  run("toggleRow('tr','matcha');"); // kapat
  assert(run('MAP.concept') === null, 'detay kapanınca Genel moda döner');
  run("toggleRow('world','dubai-cikolatasi');");
  assert(run('MAP.concept') === null, 'geo verisi olmayan kavramda harita Genel kalır');
  chip = run('mapChipHtml()');
  assert(chip.indexOf('Dubai Çikolatası — bu kavram için henüz geo verisi yok') !== -1, 'geo-yok uyarı çipi');
  assert(els.mapChip.innerHTML.indexOf('henüz geo verisi yok') !== -1, 'çip DOM\'a yazılır (updateMap)');
  run("toggleRow('world','dubai-cikolatasi');"); // kapat
  assert(run('mapChipHtml()') === '', 'uyarı çipi detay kapanınca kalkar');

  // Pencere değişimi kavram modunu sıfırlar (detay da kapanır)
  run("toggleRow('tr','matcha');MAP.concept==='matcha'");
  run("win='daily';expanded={world:null,tr:null};MAP.concept=null;MAP.notice=null;"); // bindTabs davranışı
  run("win='weekly';");

  // Ülke kartı bölümleri
  run("MAP.sel='TR';renderCcard();");
  let card = els.ccardWrap.innerHTML;
  assert(card.indexOf('💬 Bahsetmeler') !== -1, 'TR kartında Bahsetmeler bölümü var');
  assert(card.indexOf('📈 Google Trends ilgisi') !== -1, 'TR kartında Google Trends bölümü var');
  assert(card.indexOf('width:41%') !== -1 && card.indexOf('>41<') !== -1, 'TR matcha ilgi barı 41/100');
  run("MAP.sel='JP';renderCcard();");
  card = els.ccardWrap.innerHTML;
  assert(card.indexOf('💬 Bahsetmeler') === -1, 'JP (yalnız geo) kartında Bahsetmeler bölümü YOK');
  assert(card.indexOf('📈 Google Trends ilgisi') !== -1 && card.indexOf('width:95%') !== -1, 'JP kartında ilgi 95 barı');
  assert(card.indexOf('Bu ülkede henüz sinyal yok') === -1, 'JP kartı boş-durum göstermez');
  run("MAP.sel='GB';renderCcard();");
  card = els.ccardWrap.innerHTML;
  assert(card.indexOf('💬 Bahsetmeler') !== -1, 'GB (yalnız bahsetme) kartında Bahsetmeler var');
  assert(card.indexOf('📈 Google Trends ilgisi') === -1, 'GB kartında verisiz Google Trends bölümü gizli');
  run("MAP.sel=null;");

  // Tooltip önbelleği güncelleniyor mu (updateMap svg'siz erken döner; mapValues üstünden dolaylı test edildi)
  assert(run('hasGeo()') === true && run("geoFor('cortado')") === null, 'geoFor: verisiz kavram → null');

  // ── Kapsam dürüstlüğü — coverage_gaps uyarısı (üst bar) ────────────────
  run("win='weekly';render();");
  assert(els.ubGap.textContent.indexOf('4–11 Tem veri kesintisiyle kesişiyor') !== -1,
    'weekly pencere (kesişiyor) üst barda gap uyarısı gösterir');
  run("win='monthly';render();");
  assert(els.ubGap.textContent.indexOf('DEĞİŞİM oranları yanıltıcı olabilir') !== -1,
    'monthly pencere (kesişiyor) uyarı gösterir');
  run("win='daily';render();");
  assert(els.ubGap.textContent === '', 'daily pencere (15-16 Tem, kesişmiyor) uyarı GÖSTERMEZ');

  // ── '⚠ kapsam' çipi — cur<5 && prev>100 → ok yerine nötr çip ──────────
  assert(run('deltaHtml({mentions:2,prev_mentions:500})').indexOf('⚠ kapsam') !== -1,
    'cur<5 && prev>100 → ⚠ kapsam çipi');
  assert(run('deltaHtml({mentions:0,prev_mentions:500})').indexOf('⚠ kapsam') !== -1,
    'cur=0 && prev>100 → ↓ %100 yerine ⚠ kapsam çipi');
  assert(run('deltaHtml({mentions:2,prev_mentions:500})').indexOf('gerçek düşüş sanma') !== -1,
    'çipin tooltip açıklaması var');
  assert(run('deltaHtml({mentions:4,prev_mentions:100})').indexOf('kapsam') === -1,
    'prev=100 (>100 değil) → normal yüzde kuralı');
  assert(run('deltaHtml({mentions:0,prev_mentions:40})').indexOf('↓ %100') !== -1,
    'küçük prev → ↓ %100 kuralı korunur');
  assert(run('deltaHtml({mentions:500,prev_mentions:2})').indexOf('×') !== -1,
    'ters yön (küçük prev, büyük şimdi) ×N kuralı aynen kalır');
  assert(run('deltaHtml({mentions:120,prev_mentions:0})').indexOf('YENİ') !== -1,
    'YENİ kuralı aynen kalır');

  // ── Boş pencere mesajı — daily/weekly probe açıklaması, monthly genel ──
  run("win='daily';grp='tatli';");
  h = run("panelHtml('tr','TR','x')");
  assert(h.indexOf("probe kaynakları 16 Tem 2026'da devreye girdi") !== -1,
    'daily boş panel probe kaynak açıklaması gösterir');
  assert(run("win='weekly';emptyWinMsg()").indexOf('16 Tem 2026') !== -1,
    'weekly boş metni de probe açıklaması');
  assert(run("win='monthly';emptyWinMsg()") === 'Bu pencerede henüz sinyal yok.',
    'monthly boş metni genel kalır');
  run("win='weekly';grp='all';");
}

// ── 3) Gerçek kahve.json ile geriye-uyum ─────────────────────────────────
async function testRealJson() {
  console.log('# gerçek docs/data/kahve.json (geriye-uyum)');
  const data = JSON.parse(fs.readFileSync(REAL_JSON, 'utf8'));
  const page = await runPage(data);
  const { run } = page;

  for (const w of ['daily', 'weekly', 'monthly']) {
    for (const r of ['world', 'tr']) {
      run(`win='${w}';grp='all';`);
      const h = run(`panelHtml('${r}','T','x')`);
      const sig = data.items.filter((i) => i.metrics[w][r].mentions > 0).length;
      assert(countRows(h) === sig && countNosig(h) === 0,
        `${w}/${r}: görünen satır (${countRows(h)}) = sinyalli (${sig}), nosig gizli`);
    }
  }
  // coverage_gaps alanı yoksa uyarı yolu no-op kalmalı (geriye-uyum)
  if (!data.coverage_gaps) {
    run("win='weekly';render();");
    assert(run('gapsIntersecting().length') === 0 && page.els.ubGap.textContent === '',
      'coverage_gaps yok → gap uyarısı asla görünmez');
  }
  const hasGeo = run('hasGeo()');
  // geo alanı olsa da concepts boş olabilir (tüm pytrends çekimleri düşmüş
  // taze v3 çıktısı) — sayfa bu durumda v2 gibi davranmalı, test de öyle bakar.
  const geoCount = (data.geo && data.geo.concepts) ? Object.keys(data.geo.concepts).length : 0;
  if (geoCount > 0) {
    assert(hasGeo === true, 'v3 veri (geo dolu): hasGeo() true');
  } else {
    assert(hasGeo === false, 'geo alanı yok/boş → hasGeo() false (v2 davranışı)');
    assert(run('mapChipHtml()') === '', 'geo yokken çip asla görünmez');
    const first = data.items.find((i) => i.metrics.weekly.tr.mentions > 0) || data.items[0];
    run(`win='weekly';toggleRow('tr','${first.id}');`);
    assert(run('MAP.concept') === null && run('MAP.notice') === null,
      'geo yokken satır tıklaması haritaya dokunmaz');
    assert(run('mapLegendText()') === 'bahsetme yoğunluğu', 'geo yokken legend v2 anlamı');
  }
}

// ── main ──────────────────────────────────────────────────────────────────
(async () => {
  // 1) node --check: sayfa script'i sözdizimsel olarak geçerli mi?
  console.log('# node --check');
  const tmp = path.join(os.tmpdir(), 'kahve_page_script.js');
  fs.writeFileSync(tmp, extractScript());
  try {
    execFileSync(process.execPath, ['--check', tmp]);
    console.log('  ok - sayfa script sözdizimi geçerli');
  } catch (e) {
    failures++;
    console.error('  FAIL - node --check: ' + e.message);
  } finally {
    fs.unlinkSync(tmp);
  }

  await testV3();
  await testRealJson();

  if (failures) {
    console.error(`\n${failures} test BAŞARISIZ`);
    process.exit(1);
  }
  console.log('\ntüm DOM-stub testleri geçti');
})().catch((e) => { console.error(e); process.exit(1); });
