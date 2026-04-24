const $ = (id) => document.getElementById(id);

const runBtn = $('runBtn');
const loadSampleBtn = $('loadSampleBtn');
const csvUpload = $('csvUpload');
const companyText = $('companyText');
const defaultCategory = $('defaultCategory');
const delayInput = $('delay');
const statusBadge = $('statusBadge');
const progressPanel = $('progressPanel');
const resultPanel = $('resultPanel');
const progressFill = $('progressFill');
const progressText = $('progressText');
const progressCurrent = $('progressCurrent');
const statMail = $('statMail');
const statForm = $('statForm');
const statNone = $('statNone');
const resultTbody = $('resultTbody');
const dlCsvBtn = $('dlCsvBtn');
const dlXlsxBtn = $('dlXlsxBtn');

let currentJobId = null;
let stats = { mail: 0, form: 0, none: 0 };

const SAMPLE = `# サンプル: 人材系10社
リクルートホールディングス, https://recruit-holdings.com/ja/
パソナグループ, https://www.pasonagroup.co.jp/
マンパワーグループ, https://www.manpowergroup.jp/
ランスタッド, https://www.randstad.co.jp/
アデコ, https://www.adecco.co.jp/
エン・ジャパン, https://corp.en-japan.com/
マイナビ, https://www.mynavi.jp/company/
ウィルグループ, https://willgroup.co.jp/
キャリアデザインセンター, https://cdc.type.jp/
MS-Japan, https://www.jmsc.co.jp/`;

loadSampleBtn.addEventListener('click', () => {
  companyText.value = SAMPLE;
});

csvUpload.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  // BOM除去
  companyText.value = text.replace(/^﻿/, '');
});

runBtn.addEventListener('click', async () => {
  const text = companyText.value.trim();
  if (!text) {
    alert('会社名とURLを入力してください');
    return;
  }

  // リセット
  resetUI();
  runBtn.disabled = true;
  setBadge('実行中...', 'running');

  try {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        text,
        category: defaultCategory.value,
        delay: parseFloat(delayInput.value) || 2.0,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'エラーが発生しました');
      runBtn.disabled = false;
      setBadge('エラー', 'error');
      return;
    }

    currentJobId = data.job_id;
    progressPanel.style.display = 'block';
    resultPanel.style.display = 'block';
    progressText.textContent = `0 / ${data.count}`;

    // SSE受信
    const es = new EventSource(`/api/stream/${currentJobId}`);

    es.addEventListener('row', (ev) => {
      const d = JSON.parse(ev.data);
      addRow(d.index, d.row);
      const pct = (d.index / d.total) * 100;
      progressFill.style.width = `${pct}%`;
      progressText.textContent = `${d.index} / ${d.total}`;
      progressCurrent.textContent = d.row.会社名;
    });

    es.addEventListener('done', (ev) => {
      es.close();
      runBtn.disabled = false;
      setBadge('完了', 'done');
      progressCurrent.textContent = '全件完了';
      dlCsvBtn.disabled = false;
      dlXlsxBtn.disabled = false;
      dlCsvBtn.onclick = () => { window.location = `/api/download/${currentJobId}.csv`; };
      dlXlsxBtn.onclick = () => { window.location = `/api/download/${currentJobId}.xlsx`; };
    });

    es.addEventListener('error', (ev) => {
      es.close();
      runBtn.disabled = false;
      setBadge('エラー', 'error');
    });

  } catch (err) {
    alert('通信エラー: ' + err.message);
    runBtn.disabled = false;
    setBadge('エラー', 'error');
  }
});

function resetUI() {
  currentJobId = null;
  stats = { mail: 0, form: 0, none: 0 };
  progressFill.style.width = '0%';
  progressText.textContent = '0 / 0';
  progressCurrent.textContent = '';
  resultTbody.innerHTML = '';
  updateStats();
  dlCsvBtn.disabled = true;
  dlXlsxBtn.disabled = true;
}

function setBadge(text, cls) {
  statusBadge.textContent = text;
  statusBadge.className = 'badge ' + (cls || '');
}

function addRow(index, row) {
  const tr = document.createElement('tr');
  let cls = 'row-none';
  if (row.メアド) { cls = 'row-mail'; stats.mail++; }
  else if (row.問い合わせフォームURL) { cls = 'row-form'; stats.form++; }
  else { stats.none++; }
  tr.className = cls;

  const esc = (s) => (s || '').replace(/[<>&"]/g, (c) => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));

  tr.innerHTML = `
    <td>${index}</td>
    <td><strong>${esc(row.会社名)}</strong></td>
    <td><a href="${esc(row.公式サイトURL)}" target="_blank" rel="noopener">${esc(row.公式サイトURL).replace(/https?:\/\//, '').slice(0, 35)}</a></td>
    <td>${row.メアド ? `<code>${esc(row.メアド)}</code>` : '<span style="color:#ccc">—</span>'}</td>
    <td>${row.問い合わせフォームURL ? `<a href="${esc(row.問い合わせフォームURL)}" target="_blank" rel="noopener">${esc(row.問い合わせフォームURL).replace(/https?:\/\//, '').slice(0, 30)}</a>` : '<span style="color:#ccc">—</span>'}</td>
    <td>${row.業種 ? `<span class="tag">${esc(row.業種)}</span>` : ''}</td>
    <td style="font-size:11px;color:#888;">${esc(row.備考)}</td>
  `;
  resultTbody.appendChild(tr);
  updateStats();
}

function updateStats() {
  statMail.textContent = stats.mail;
  statForm.textContent = stats.form;
  statNone.textContent = stats.none;
}
