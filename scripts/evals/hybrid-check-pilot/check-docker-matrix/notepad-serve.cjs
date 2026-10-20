// SPDX-License-Identifier: Apache-2.0
const fs = require('node:fs');
const express = require('/app/node_modules/express');
const bodyParser = require('/app/node_modules/body-parser');
const sequelize = require('/app/config/database');
const app = express();
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({extended: true}));
app.use((req, res, next) => {
  const body = req.body;
  res.on('finish', () => fs.appendFileSync('/app-out/requests.jsonl', JSON.stringify({method: req.method, path: req.path, body, status: res.statusCode}) + '\n'));
  next();
});
app.use('/images', express.static('/app/images'));
app.set('view engine', 'ejs');
app.set('views', '/app/views');
app.use('/', require('/app/routes/note'));
let server;
sequelize.sync().then(async () => {
  await sequelize.query('PRAGMA journal_mode=DELETE');
  server = app.listen(3000, '127.0.0.1', () => fs.writeFileSync('/app-out/server-ready.json', JSON.stringify({pid: process.pid, host: '127.0.0.1', port: 3000})));
}).catch(error => { console.error(error); process.exitCode = 1; });
process.on('SIGTERM', () => {
  if (!server) return process.exit(2);
  server.close(async error => {
    try {
      if (error) throw error;
      await sequelize.close();
      fs.writeFileSync('/app-out/server-stopped.json', JSON.stringify({pid: process.pid, serverClosed: true, databaseClosed: true}));
      process.exit(0);
    } catch (error) { console.error(error); process.exit(2); }
  });
  server.closeIdleConnections();
});
