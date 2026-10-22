// ============================================================
//  Скрипт для Google Таблицы: принимает заявки от бота.
//  Вставить: Таблица → Расширения → Apps Script.
//  Придумайте свой секретный ключ и впишите его сюда и в .env бота.
// ============================================================

const SECRET = 'придумайте-свой-ключ-123';

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    if (data.secret !== SECRET) {
      return reply({ ok: false, error: 'wrong secret' });
    }
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];

    // Пустая таблица — создаём заголовки
    if (sheet.getLastRow() === 0 && data.columns) {
      sheet.appendRow(data.columns);
      sheet.getRange(1, 1, 1, data.columns.length)
           .setFontWeight('bold')
           .setBackground('#d9ebfa');
      sheet.setFrozenRows(1);
    }

    sheet.appendRow(data.row);
    return reply({ ok: true });
  } catch (err) {
    return reply({ ok: false, error: String(err) });
  }
}

function reply(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
