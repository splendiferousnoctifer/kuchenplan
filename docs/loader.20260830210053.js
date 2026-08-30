import DATA from "./data.20260830210053.js";
import { boot, esc } from "./app.js?v=20260830210053";

boot(DATA).catch((err) => {
  document.querySelector("main").innerHTML =
    `<p style="color:#8a3a12">Daten konnten nicht geladen werden: ${esc(err.message)}</p>`;
});
