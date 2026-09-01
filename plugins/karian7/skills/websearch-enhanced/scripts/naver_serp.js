(() => {
  const clean = s => (s || '').replace(/새 창 열림/g, '').replace(/\s+/g, ' ').trim();
  const SKIP = /(keep|help|search|nid|note|blog|cafe|shopping|m)\.naver\.com|naver\.me|malls\./;
  const out = [];
  const seen = new Set();
  document.querySelectorAll('.fds-news-item-list-tab').forEach(root => {
    Array.from(root.children).forEach(item => {
      const lines = (item.innerText || '').split('\n').map(s => s.trim()).filter(Boolean)
        .filter(s => !['새 창 열림', '네이버뉴스', '언론사 선정', '보도자료', '자동생성기사'].includes(s));
      const dateLine = lines.find(s => /^\d+(시간|분|일|주|개월)\s*전$/.test(s) || /^\d{4}\.\d{2}\.\d{2}\.?$/.test(s)) || '';
      const press = lines[0] && lines[0] !== dateLine ? lines[0] : '';
      const links = Array.from(item.querySelectorAll('a[href^=http]'))
        .filter(a => !SKIP.test(a.href))
        .map(a => ({ a, t: clean(a.innerText) }))
        .filter(x => x.t.length > 8 && x.t !== press);
      if (!links.length) return;
      const title = links[0].t;
      const url = links[0].a.href.split('#')[0];
      if (seen.has(url)) return;
      seen.add(url);
      const desc = lines.map(clean)
        .filter(s => s !== press && s !== dateLine && s !== title && s.length > 20)
        .sort((a, b) => b.length - a.length)[0] || '';
      out.push({ title, url, press, date_label: dateLine, desc: desc.slice(0, 300) });
    });
  });
  return out;
})()
