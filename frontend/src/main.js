import { mount } from 'svelte';
import './app.css';
// @ts-ignore
import App from './App.svelte';

const targetElement = document.getElementById('app');

if (!targetElement) {
  throw new Error("No se encontró el elemento raíz con el id 'app'");
}

const app = mount(App, {
  target: targetElement,
});

export default app;