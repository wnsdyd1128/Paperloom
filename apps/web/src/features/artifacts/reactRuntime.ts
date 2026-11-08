/**
 * React 아티팩트의 격리 문서(frameDocument.reactDocument)에 넣는 React·ReactDOM. 웹앱과 같은 React를 따로 한 파일로 묶어
 * (preview.ts가 `?worker&url`로 그 묶음을 받는다) 전역 React·ReactDOM으로 둔다. 격리 문서는 바깥 주소를 불러오지 못하므로
 * 웹앱이 이 파일의 글을 받아 문서 안에 넣는다.
 */
import * as React from "react";
import * as ReactDOMClient from "react-dom/client";

Object.assign(globalThis, { React, ReactDOM: ReactDOMClient });
