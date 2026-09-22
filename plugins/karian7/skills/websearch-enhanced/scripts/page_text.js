(() => {
  // 브라우저 폴백용 본문 추출. 정적 수집이 껍데기만 받아온 페이지에서만 쓴다.
  // 렌더링이 끝난 DOM 을 보므로 JS 로 그려지는 본문과 iframe 안 본문을 잡는다.
  const DROP = 'script,style,nav,header,footer,aside,form,noscript';

  const readable = doc => {
    if (!doc || !doc.body) return '';
    const clone = doc.body.cloneNode(true);
    clone.querySelectorAll(DROP).forEach(n => n.remove());
    return (clone.innerText || '').replace(/\n{2,}/g, '\n').trim();
  };

  let text = readable(document);
  let source = 'document';

  // 같은 출처의 iframe 안에 본문을 넣는 CMS(네이버 블로그 #mainFrame 등).
  // 상위 문서보다 긴 본문이 있으면 그쪽을 쓴다.
  for (const frame of Array.from(document.querySelectorAll('iframe'))) {
    let inner = '';
    try { inner = readable(frame.contentDocument); } catch (e) { continue; }
    if (inner.length > text.length) { text = inner; source = 'iframe:' + (frame.id || frame.name || '?'); }
  }

  return { title: document.title || '', text, source };
})()
