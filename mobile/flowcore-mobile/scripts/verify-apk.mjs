import { createHash } from "node:crypto";
import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const input = process.argv[2];
if (!input) {
  console.error("Uso: pnpm apk:verify caminho/para/FlowCore.apk");
  process.exit(1);
}

const apkPath = resolve(input);
if (extname(apkPath).toLowerCase() !== ".apk" || !existsSync(apkPath)) {
  console.error("Informe um arquivo .apk existente.");
  process.exit(1);
}

const size = statSync(apkPath).size;
if (size <= 0) {
  console.error("O APK está vazio.");
  process.exit(1);
}

const archiveCheck = spawnSync("unzip", ["-t", apkPath], { stdio: "inherit" });
if (archiveCheck.status !== 0) {
  console.error("A estrutura ZIP do APK não passou na validação.");
  process.exit(archiveCheck.status ?? 1);
}

const sha256 = await new Promise((resolveHash, reject) => {
  const hash = createHash("sha256");
  createReadStream(apkPath).on("data", chunk => hash.update(chunk)).on("end", () => resolveHash(hash.digest("hex"))).on("error", reject);
});

console.log("\nAPK validado");
console.log(`Arquivo: ${apkPath}`);
console.log(`Tamanho: ${size} bytes`);
console.log(`SHA-256: ${sha256}`);
