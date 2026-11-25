import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import Display from './Display.jsx';
import './style.css';
createRoot(document.getElementById('root')).render(location.hash === '#display' ? <Display /> : <App />);
