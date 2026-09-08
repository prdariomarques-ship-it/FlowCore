import { spawnSync } from "node:child_process";

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit", shell: true });
  if (result.error) {
    console.error(`\nFalha ao executar '${command} ${args.join(" ")}': ${result.error.message}\n`);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}

console.log("\nFlowCore Mobile — build APK de distribuição interna\n");
console.log("O perfil preview gera um arquivo .apk instalável. Não substitua este resultado por preview web, QR code ou checkpoint.\n");

run("pnpm", ["check"]);
run("pnpm", ["test"]);

const account = spawnSync("npx", ["eas-cli@latest", "whoami"], { encoding: "utf8", shell: true });
if (account.status !== 0) {
  console.error("\nA conta Expo ainda não está autenticada. Execute: npx eas-cli@latest login\n");
  process.exit(account.status ?? 1);
}

console.log(`Conta Expo: ${account.stdout.trim()}`);
run("npx", ["eas-cli@latest", "build", "--platform", "android", "--profile", "preview"]);
