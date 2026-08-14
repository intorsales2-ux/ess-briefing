/** 인투알 브리핑 — 댓글 우체통 v2 (이름·비밀번호식, JSONP)
 * 설치: 구글 시트 → 확장 프로그램 → Apps Script → 전체 붙여넣기 → 배포(웹 앱 · 액세스: 모든 사용자)
 * v1과 교체 시: 기존 배포 관리에서 '새 버전'으로 재배포하면 URL 유지됩니다. */
var SHEET = '댓글';

function _sheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET) || ss.insertSheet(SHEET);
  if (sh.getLastRow() === 0) sh.appendRow(['id', '시각', '호수', '이름', 'pw해시', '내용']);
  return sh;
}
function _hash(pw) {
  var raw = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, pw, Utilities.Charset.UTF_8);
  return raw.map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
}
function _out(cb, obj) {
  cb = (cb || '__cb').replace(/[^\w$]/g, '');
  return ContentService.createTextOutput(cb + '(' + JSON.stringify(obj) + ')')
    .setMimeType(ContentService.MimeType.JAVASCRIPT);
}

function doGet(e) {
  var p = e.parameter, cb = p.callback, mode = p.mode || 'list', sh = _sheet();
  if (p.hp) return _out(cb, { ok: false });                       // 스팸 봇
  if (mode === 'add') {
    var text = (p.text || '').toString().slice(0, 500).trim();
    var pw = (p.pw || '').toString();
    if (!text || pw.length < 4) return _out(cb, { ok: false, error: 'input' });
    var id = Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36);
    sh.appendRow([id, Utilities.formatDate(new Date(), 'Asia/Seoul', 'MM/dd HH:mm'),
                  (p.issue || '').toString().slice(0, 30),
                  (p.name || '익명').toString().slice(0, 20), _hash(pw), text]);
    return _out(cb, { ok: true, id: id });
  }
  if (mode === 'edit' || mode === 'del') {
    var rows = sh.getDataRange().getValues();
    for (var i = 1; i < rows.length; i++) {
      if (rows[i][0] === p.id) {
        if (rows[i][4] !== _hash((p.pw || '').toString())) return _out(cb, { ok: false, error: 'pw' });
        if (mode === 'del') sh.deleteRow(i + 1);
        else sh.getRange(i + 1, 6).setValue((p.text || '').toString().slice(0, 500).trim());
        return _out(cb, { ok: true });
      }
    }
    return _out(cb, { ok: false, error: 'notfound' });
  }
  var issue = (p.issue || '').toString();
  var list = sh.getDataRange().getValues().slice(1)
    .filter(function (r) { return !issue || r[2] === issue; })
    .map(function (r) { return { id: r[0], time: r[1], issue: r[2], name: r[3], text: r[5] }; });
  return _out(cb, { ok: true, rows: list });
}
