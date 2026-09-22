(() => {
  // 브라우저 폴백용 본문 추출. 정적 수집이 껍데기만 받아온 페이지에서만 쓴다.
  // 렌더링이 끝난 DOM 을 보므로 JS 로 그려지는 본문과 iframe 안 본문을 잡는다.
  const DROP = 'script,style,nav,header,footer,aside,form,noscript';

  // 본문 컨테이너. "가장 긴 문서"를 고르는 방식은 chrome 이 두꺼운 페이지에서 무너진다 —
  // 네이버 카페는 상위 문서가 183,643자(GNB·메뉴)인데 본문 iframe 은 2,072자였다
  // (2026-09-22 실측). 컨테이너를 먼저 찾고, 못 찾을 때만 길이로 고른다.
  const ARTICLE = ['.se-main-container', '#tbody', '.article_viewer'];

  const readable = doc => {
    if (!doc || !doc.body) return '';
    const clone = doc.body.cloneNode(true);
    clone.querySelectorAll(DROP).forEach(n => n.remove());
    return (clone.innerText || '').replace(/\n{2,}/g, '\n').trim();
  };

  const sameOriginDocs = () => {
    const docs = [{ doc: document, label: 'document' }];
    for (const frame of Array.from(document.querySelectorAll('iframe'))) {
      let inner = null;
      try { inner = frame.contentDocument; } catch (e) { continue; }
      if (inner) docs.push({ doc: inner, label: 'iframe:' + (frame.id || frame.name || '?') });
    }
    return docs;
  };

  const docs = sameOriginDocs();

  // 1순위 — 본문 컨테이너를 가진 문서.
  for (const selector of ARTICLE) {
    for (const { doc, label } of docs) {
      const node = doc.querySelector(selector);
      if (!node) continue;
      const clone = node.cloneNode(true);
      clone.querySelectorAll(DROP).forEach(n => n.remove());
      const text = (clone.innerText || '').replace(/\n{2,}/g, '\n').trim();
      if (text) return { title: document.title || '', text, source: label + ' ' + selector };
    }
  }

  // 2순위 — 가장 긴 문서. 상위 문서와 같은 출처 iframe 중에서 고른다.
  let best = { text: '', label: 'document' };
  for (const { doc, label } of docs) {
    const text = readable(doc);
    if (text.length > best.text.length) best = { text, label };
  }
  return { title: document.title || '', text: best.text, source: best.label };
})()
