-- Obsidian/GitHub-style callouts (> [!type] title\n> body) → <div class="callout callout-<type>">
local TYPES = {
  note=true, tip=true, important=true, warning=true, caution=true,
  info=true, success=true, question=true, example=true, quote=true,
  abstract=true, todo=true, failure=true, danger=true, bug=true, hint=true,
}

function BlockQuote(el)
  local first = el.content[1]
  if not first or first.t ~= "Para" then return nil end
  local inlines = first.content
  if #inlines == 0 then return nil end

  -- 첫 inline이 Str("[!type]") 패턴인지 확인
  local kind, consumed
  if inlines[1].t == "Str" then
    kind = inlines[1].text:match("^%[!([%w]+)%]$")
    if kind then consumed = 1 end
  end
  if not kind then return nil end                       -- 일반 인용문 → 그대로 유지

  local lower = kind:lower()
  if not TYPES[lower] then return nil end               -- 알 수 없는 타입도 그대로 유지

  -- 마커 뒤 공백 스킵
  while inlines[consumed + 1] and inlines[consumed + 1].t == "Space" do
    consumed = consumed + 1
  end

  -- 첫 SoftBreak/LineBreak 전까지 = 제목
  local title_inlines, i = {}, consumed + 1
  while i <= #inlines do
    local inl = inlines[i]
    if inl.t == "SoftBreak" or inl.t == "LineBreak" then
      i = i + 1
      break
    end
    table.insert(title_inlines, inl)
    i = i + 1
  end

  -- 나머지 = 본문 첫 단락
  local body_inlines = {}
  while i <= #inlines do
    table.insert(body_inlines, inlines[i])
    i = i + 1
  end

  local body_blocks = {}
  if #body_inlines > 0 then
    table.insert(body_blocks, pandoc.Para(body_inlines))
  end
  for j = 2, #el.content do                             -- 두 번째 단락 이후
    table.insert(body_blocks, el.content[j])
  end

  -- 제목 미지정 시 타입명을 캐피털라이즈하여 기본 제목으로
  if #title_inlines == 0 then
    title_inlines = { pandoc.Str(lower:sub(1,1):upper() .. lower:sub(2)) }
  end

  local title_div = pandoc.Div(
    { pandoc.Plain(title_inlines) },
    pandoc.Attr("", {"callout-title"}, {})
  )
  local body_div = pandoc.Div(body_blocks, pandoc.Attr("", {"callout-body"}, {}))
  return pandoc.Div(
    { title_div, body_div },
    pandoc.Attr("", {"callout", "callout-" .. lower}, { ["data-callout"] = lower })
  )
end
