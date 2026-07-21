/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The React entry point — mounts <Atlas> into the DOM inside the Redux
 * <Provider> and React StrictMode.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Provider } from 'react-redux'
import './index.css'
import Atlas from './Atlas.tsx'
import { store } from './store'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Provider store={store}>
      <Atlas />
    </Provider>
  </StrictMode>,
)
