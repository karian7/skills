(() => {
  // 웹문서 탭(where=web) SERP 추출기.
  // 뉴스 탭과 DOM 구조가 다르다 — `.fds-news-item-list-tab` 컨테이너가 없어
  // naver_serp.js 를 그대로 쓰면 항상 0건이 나온다(2026-09-22 실측).
  // 웹문서 탭은 결과 블록의 클래스명이 자주 바뀌므로, 컨테이너 셀렉터 대신
  // "같은 href 를 가리키는 앵커들"을 묶어 제목·설명을 복원한다.
  const clean = s => (s || '').replace(/새 창 열림/g, '').replace(/\s+/g, ' ').trim();

  // 네이버 호스트는 기본 제외하되, 검색 결과로 유효한 콘텐츠 호스트만 남긴다.
  // (mail·notify·talks·keep·nid 등 로그인 상태에 따라 붙는 내비 링크를 걷어내는 용도)
  const KEEP_NAVER = /^(m\.)?(blog|post|cafe|news|kin|terms|in)\.naver\.com$/;
  const isNaver = host => /(^|\.)naver\.com$/.test(host);
  const SKIP_URL = /naver\.me|\/sorry\/|malls\./;
  const HOSTNAME = /^[a-z0-9.-]+\.[a-z]{2,}$/i;
  const DATE = /(^|\s)(\d{4}\.\d{2}\.\d{2}\.?|\d+(시간|분|일|주|개월)\s*전)/;

  const groups = new Map();
  document.querySelectorAll('a[href^="http"]').forEach(a => {
    let host;
    try { host = new URL(a.href).hostname.toLowerCase(); } catch (e) { return; }
    if (isNaver(host) && !KEEP_NAVER.test(host)) return;
    if (SKIP_URL.test(a.href)) return;
    const text = clean(a.innerText);
    if (text.length < 8) return;
    const url = a.href.split('#')[0];
    if (!groups.has(url)) groups.set(url, []);
    groups.get(url).push(text);
  });

  const out = [];
  groups.forEach((texts, url) => {
    // 브레드크럼 줄("site.com›경로")은 출처, 가장 긴 줄은 설명, 나머지 중 짧은 쪽이 제목.
    // 브레드크럼 앞부분은 "매체명 도메인" 또는 "도메인 도메인" 꼴이다. 뒤쪽 도메인은 버린다.
    const crumb = texts.find(t => t.includes('›')) || '';
    const crumbWords = crumb ? crumb.split('›')[0].trim().split(' ').filter(Boolean) : [];
    if (crumbWords.length > 1 && HOSTNAME.test(crumbWords[crumbWords.length - 1])) crumbWords.pop();
    const press = crumbWords.join(' ');
    const body = texts.filter(t => t !== crumb);
    if (!body.length) return;
    const byLength = body.slice().sort((x, y) => y.length - x.length);
    const desc = byLength[0];
    const title = byLength[byLength.length - 1];
    const dateHit = DATE.exec(desc);
    out.push({
      title: title.slice(0, 200),
      url,
      press,
      date_label: dateHit ? dateHit[2] : '',
      desc: desc.replace(DATE, '').trim().slice(0, 300),
    });
  });
  return out;
})()
