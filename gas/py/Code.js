/**
 * 파이썬 4반 성적 시트 관리 (정렬 + 구조 방어)
 * score 탭을 주차 역순 → 학번 오름차순으로 정렬하고,
 * 허용되지 않은 탭 생성을 자동 차단합니다.
 */

const SCORE_TAB_NAME = "score";

/**
 * 4반 시트 기준 공식 탭 목록 및 고정 순서
 */
const ALLOWED_SHEET_ORDER = [
  "progress",
  "resource",
  "발표",
  "score",
  "agenda",
  "상호평가 제출자 답",
  "grade",
  "상호평가",
  "Q&A"
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("관리자 설정")
    .addItem("⚡ 자동 정렬 + 시트 구조 방어(onChange) 트리거 켜기", "createOnChangeTrigger")
    .addSeparator()
    .addItem("🔄 score 탭 정렬 (주차↓ 학번↑)", "sortScoreTab")
    .addItem("🔄 시트 순서 지금 정렬 및 미허용 탭 삭제", "manualEnforceStructure")
    .addSeparator()
    .addItem("🔒 progress 보호 설정 (고정열 + 과거 주차 잠금)", "protectProgressTab")
    .addItem("🔄 progress 한타/wpm 컬럼 주차 오름차순 재배치", "reorderProgressColumns")
    .addItem("🔒 발표 탭 전체 보호", "protectPresentationTab")
    .addToUi();
}

/**
 * onChange 이벤트 설치형 트리거를 생성합니다.
 * 최초 1회만 실행하면 이후 score 탭 자동 정렬이 활성화됩니다.
 */
function createOnChangeTrigger() {
  const triggers = ScriptApp.getProjectTriggers();
  for (const trigger of triggers) {
    if (trigger.getHandlerFunction() === "onSpreadsheetChange") {
      ScriptApp.deleteTrigger(trigger);
    }
  }
  ScriptApp.newTrigger("onSpreadsheetChange")
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onChange()
    .create();
  SpreadsheetApp.getUi().alert("⚡ onChange 트리거가 성공적으로 활성화되었습니다.\nscore 탭 자동 정렬이 켜졌습니다.");
}

/**
 * 스프레드시트 onChange 통합 핸들러.
 * 1) 임의 시트 생성 감지 시 삭제 & 탭 순서 강제 복구
 * 2) score 탭 자동 정렬 (API 업로드 후 60초 쓰로틀)
 */
function onSpreadsheetChange(e) {
  try {
    enforceWorkbookStructure(e);
  } catch (err) {
    console.error("시트 구조 방어 실행 중 오류:", err);
  }

  try {
    autoSortScoreTabSilent();
  } catch (err) {
    console.error("score 탭 자동 정렬 중 오류:", err);
  }
}

/**
 * score 탭을 자동 정렬합니다. (60초 쓰로틀 — 연속 이벤트 중복 실행 방지)
 * UI alert 없이 조용히 실행되며, 수동 실행은 sortScoreTab() 메뉴를 사용합니다.
 */
function autoSortScoreTabSilent() {
  const THROTTLE_MS = 60 * 1000;
  const props = PropertiesService.getScriptProperties();
  const lastSort = parseInt(props.getProperty("LAST_SCORE_SORT_TS") || "0");
  const now = Date.now();
  if (now - lastSort < THROTTLE_MS) {
    console.log("score 자동 정렬 스킵 (60초 이내 중복 실행 방지)");
    return;
  }
  props.setProperty("LAST_SCORE_SORT_TS", String(now));

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SCORE_TAB_NAME);
  if (!sheet) return;

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2) return;

  const dataRange = sheet.getRange(2, 1, lastRow - 1, lastCol);
  dataRange.sort([
    { column: 2, ascending: false },
    { column: 7, ascending: true },
    { column: 8, ascending: true },
    { column: 3, ascending: true },
  ]);

  const total = lastRow - 1;
  console.log(`[자동 정렬] score 탭 ${total}행 정렬 완료 (원래 No 값 유지)`);
}

/**
 * progress 탭 표준 보호 설정 (파이썬 4반)
 * - 1-4행 (mean, stdev, count, 헤더): 보호
 * - A-P열 (학번, 이름, 진도 수식열): 보호
 * - 과거 주차 학생 입력 영역: 빈 컬럼 기준 2개 이전까지 자동 잠금
 * - 현재 주차(빈 컬럼 직전 2개) + 미래(빈 컬럼 이후): 편집 허용
 */
function protectProgressTab() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const me = Session.getEffectiveUser();
  const sheet = ss.getSheetByName("progress");
  const FIXED_COLS = 16; // A-P열 (1-16)

  if (!sheet) {
    SpreadsheetApp.getUi().alert('"progress" 탭을 찾을 수 없습니다.');
    return;
  }

  // 기존 progress 탭의 보호 범위 전부 정리
  const existing = ss.getProtections(SpreadsheetApp.ProtectionType.RANGE);
  for (const p of existing) {
    if (p.getRange().getSheet().getName() === "progress") {
      const desc = p.getDescription();
      if (desc === "PROGRESS_STATS_AND_HEADER" ||
          desc === "PROGRESS_FIXED_COLS" ||
          desc === "PROGRESS_PAST_WEEKS" ||
          desc.includes("progress")) {
        p.remove();
      }
    }
  }

  // 1. 1-4행 보호 (통계 및 헤더)
  const headerRange = sheet.getRange(1, 1, 4, sheet.getMaxColumns());
  const headerProtection = headerRange.protect();
  headerProtection.setDescription("PROGRESS_STATS_AND_HEADER");
  headerProtection.removeEditors(headerProtection.getEditors());
  headerProtection.addEditor(me);
  if (headerProtection.canDomainEdit()) headerProtection.setDomainEdit(false);

  // 2. A-P열 (1-16열) 보호 (학번, 이름, 진도 수식)
  const fixedColsRange = sheet.getRange(1, 1, sheet.getMaxRows(), FIXED_COLS);
  const fixedColsProtection = fixedColsRange.protect();
  fixedColsProtection.setDescription("PROGRESS_FIXED_COLS");
  fixedColsProtection.removeEditors(fixedColsProtection.getEditors());
  fixedColsProtection.addEditor(me);
  if (fixedColsProtection.canDomainEdit()) fixedColsProtection.setDomainEdit(false);

  // 3. 과거 주차 자동 잠금 (빈 컬럼 기준 2개 이전까지)
  const studentStartCol = FIXED_COLS + 1; // Q열 = 17
  const lastCol = sheet.getLastColumn();
  let pastLockInfo = "없음 (학생 입력 영역 미감지)";

  if (lastCol >= studentStartCol) {
    const numStudentCols = lastCol - studentStartCol + 1;
    // 4행(헤더)과 5-10행(학생 데이터 샘플) 읽기
    const headers = sheet.getRange(4, studentStartCol, 1, numStudentCols).getValues()[0];
    const sampleRows = sheet.getRange(5, studentStartCol,
      Math.min(6, sheet.getLastRow() - 4), numStudentCols).getValues();

    // 각 컬럼이 데이터를 가지고 있는지 확인
    let firstEmptyIdx = numStudentCols; // 기본값: 전부 채워짐
    for (let c = 0; c < numStudentCols; c++) {
      const headerVal = String(headers[c] || "").trim();
      if (!headerVal) {
        firstEmptyIdx = c;
        break;
      }
      // 헤더는 있지만 학생 데이터가 전부 비어있으면 빈 컬럼
      const hasData = sampleRows.some(row => {
        const v = row[c];
        return v !== "" && v !== null && v !== undefined;
      });
      if (!hasData) {
        firstEmptyIdx = c;
        break;
      }
    }

    // 빈 컬럼 기준 2개 이전까지가 과거 → 잠금 대상
    // 예: 빈 컬럼 idx=4 → 0,1 잠금 (2,3은 현재 주차로 개방)
    const lockCount = firstEmptyIdx - 2;

    if (lockCount > 0) {
      const pastRange = sheet.getRange(5, studentStartCol,
        sheet.getMaxRows() - 4, lockCount);
      const pastProtection = pastRange.protect();
      pastProtection.setDescription("PROGRESS_PAST_WEEKS");
      pastProtection.removeEditors(pastProtection.getEditors());
      pastProtection.addEditor(me);
      if (pastProtection.canDomainEdit()) pastProtection.setDomainEdit(false);

      // 잠금된 컬럼 헤더명 추출
      const lockedHeaders = headers.slice(0, lockCount).map(h => String(h).trim());
      const openHeaders = headers.slice(lockCount, firstEmptyIdx).map(h => String(h).trim());
      pastLockInfo = `잠금: ${lockedHeaders.join(", ")} | 개방: ${openHeaders.join(", ")}`;
    } else {
      pastLockInfo = "과거 주차 없음 (데이터 컬럼 2개 이하)";
    }
  }

  SpreadsheetApp.getUi().alert(
    "✅ progress 탭 보호 설정 완료\n" +
    "- 1-4행 (통계 및 헤더) 보호 완료\n" +
    "- A-P열 (학번/성명/진도) 보호 완료\n" +
    "- 과거 주차: " + pastLockInfo
  );
}

/**
 * progress 탭의 학생 입력 컬럼(한타/wpm)을 주차 오름차순으로 재배치
 * 한타 그룹, wpm 그룹 각각 내부에서 주차 번호 순으로 정렬
 * 예: 한타15,한타14,...,한타06 → 한타06,한타07,...,한타15
 */
function reorderProgressColumns() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("progress");
  const STUDENT_START_COL = 17; // Q열 (py 기준)

  if (!sheet) {
    SpreadsheetApp.getUi().alert('"progress" 탭을 찾을 수 없습니다.');
    return;
  }

  const lastCol = sheet.getLastColumn();
  if (lastCol < STUDENT_START_COL) {
    SpreadsheetApp.getUi().alert("학생 입력 영역이 없습니다.");
    return;
  }

  const numCols = lastCol - STUDENT_START_COL + 1;
  const numRows = sheet.getLastRow();
  if (numRows < 1) return;

  // 전체 학생 입력 영역 읽기 (1행~마지막행, 통계+헤더+데이터 모두)
  const range = sheet.getRange(1, STUDENT_START_COL, numRows, numCols);
  const allData = range.getValues();

  // 4행(index 3)이 실제 컬럼 헤더
  const headerRow = allData[3] || allData[0];

  // 컬럼을 그룹별로 분류 (한타, wpm, 기타)
  const hantaCols = [];
  const wpmCols = [];
  const otherCols = [];

  for (let i = 0; i < numCols; i++) {
    const h = String(headerRow[i] || "").trim();
    const hantaMatch = h.match(/^한타(\d+)$/);
    const wpmMatch = h.match(/^wpm(\d+)$/i);
    if (hantaMatch) {
      hantaCols.push({ idx: i, week: parseInt(hantaMatch[1], 10) });
    } else if (wpmMatch) {
      wpmCols.push({ idx: i, week: parseInt(wpmMatch[1], 10) });
    } else {
      otherCols.push({ idx: i });
    }
  }

  // 주차 오름차순 정렬
  hantaCols.sort((a, b) => a.week - b.week);
  wpmCols.sort((a, b) => a.week - b.week);

  // 새 순서: 한타 오름차순 → wpm 오름차순 → 기타
  const newOrder = [
    ...hantaCols.map(c => c.idx),
    ...wpmCols.map(c => c.idx),
    ...otherCols.map(c => c.idx)
  ];

  // 이미 올바른 순서인지 확인
  const isAlreadySorted = newOrder.every((v, i) => v === i);
  if (isAlreadySorted) {
    SpreadsheetApp.getUi().alert("ℹ️ 컬럼이 이미 오름차순으로 정렬되어 있습니다.");
    return;
  }

  // 전체 데이터를 새 순서로 재배치
  const newData = allData.map(row => newOrder.map(colIdx => row[colIdx]));
  range.setValues(newData);

  const hantaList = hantaCols.map(c => "한타" + String(c.week).padStart(2, "0")).join(", ");
  const wpmList = wpmCols.map(c => "wpm" + String(c.week).padStart(2, "0")).join(", ");

  SpreadsheetApp.getUi().alert(
    "✅ progress 컬럼 재배치 완료 (주차 오름차순)\n" +
    "- 한타: " + hantaList + "\n" +
    "- wpm: " + wpmList +
    (otherCols.length > 0 ? "\n- 기타: " + otherCols.length + "개 컬럼 (끝에 배치)" : "")
  );
}


/**
 * score 탭을 정렬합니다.
 * 정렬 기준: 1차 주차(B열) 역순 → 2차 유형1(G열) → 3차 유형2(H열) → 4차 학번(C열) 오름차순
 * 원래 No 번호를 유지합니다.
 */
function sortScoreTab() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SCORE_TAB_NAME);

  if (!sheet) {
    SpreadsheetApp.getUi().alert("score 탭을 찾을 수 없습니다.");
    return;
  }

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();

  if (lastRow < 2) {
    SpreadsheetApp.getUi().alert("정렬할 데이터가 없습니다.");
    return;
  }

  // 헤더 제외, 2행부터 데이터 범위
  const dataRange = sheet.getRange(2, 1, lastRow - 1, lastCol);

  // 정렬: B열(주차) 역순 → G열(유형1) → H열(유형2) → C열(학번)
  dataRange.sort([
    { column: 2, ascending: false }, // 주차 역순
    { column: 7, ascending: true },  // 유형1 (G열)
    { column: 8, ascending: true },  // 유형2 (H열)
    { column: 3, ascending: true },  // 학번 (C열)
  ]);

  const total = lastRow - 1;
  SpreadsheetApp.getUi().alert(
    "✅ score 탭 정렬 완료\n" +
    `${total}행 정렬 (주차 역순 → 학번 오름차순)\n` +
    "원래 No 번호 유지"
  );
}

/**
 * 허용되지 않은 새 시트가 생성되었는지 검사하여 즉시 삭제하고,
 * 탭 순서가 바뀌었을 경우 ALLOWED_SHEET_ORDER 순서대로 강제 원복합니다.
 */
function enforceWorkbookStructure(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = ss.getSheets();

  // 1. 허용되지 않은 새 시트가 생성되었는지 검사 후 즉시 삭제
  for (let i = sheets.length - 1; i >= 0; i--) {
    const sheet = sheets[i];
    const sheetName = sheet.getName();

    // 공식 목록에 없는 탭(새로 만든 탭)이면 삭제
    if (!ALLOWED_SHEET_ORDER.includes(sheetName)) {
      if (ss.getSheets().length > 1) {
        console.warn(`[구조 방어] 허용되지 않은 탭 감지 및 삭제: ${sheetName}`);
        ss.deleteSheet(sheet);
      }
    }
  }

  // 2. 탭 순서 강제 원복
  let targetIndex = 1;
  ALLOWED_SHEET_ORDER.forEach(name => {
    const sheet = ss.getSheetByName(name);
    if (sheet) {
      sheet.activate();
      ss.moveActiveSheet(targetIndex);
      targetIndex++;
    }
  });
}

/**
 * 관리자 메뉴에서 수동으로 시트 순서 정렬 및 비인가 탭 삭제를 실행합니다.
 */
function manualEnforceStructure() {
  enforceWorkbookStructure(null);
  SpreadsheetApp.getUi().alert("✅ 탭 순서 정렬 및 미허용 탭 정리가 완료되었습니다.");
}

/**
 * 발표 탭 보호 설정
 * - 시트 전체를 보호하여 학생 편집 차단 (관리자만 편집 가능)
 */
function protectPresentationTab() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const me = Session.getEffectiveUser();
  const sheet = ss.getSheetByName("발표");
  
  if (!sheet) {
    SpreadsheetApp.getUi().alert('"발표" 탭을 찾을 수 없습니다.');
    return;
  }
  
  const protection = sheet.protect().setDescription("PRESENTATION_TAB");
  protection.removeEditors(protection.getEditors());
  protection.addEditor(me);
  if (protection.canDomainEdit()) protection.setDomainEdit(false);
  
  SpreadsheetApp.getUi().alert("✅ 발표 탭 전체 보호 설정 완료 (학생 편집 차단)");
}
