import { execSync } from 'child_process'
import * as fs from 'fs'
import * as path from 'path'

const AUTH_DIR = path.join(__dirname, 'playwright', '.auth')

export default async function globalSetup() {
  fs.mkdirSync(AUTH_DIR, { recursive: true })

  const output = execSync(
    'python -m scripts.e2e_seed',
    {
      cwd: path.join(__dirname, '..', 'backend'),
      env: { ...process.env },
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'inherit'],
    }
  )

  const { admin_token, developer_token } = JSON.parse(output.trim())

  const makeStorageState = (token: string) => ({
    cookies: [],
    origins: [
      {
        origin: 'http://localhost:5173',
        localStorage: [
          { name: 'devpulse_token', value: token },
        ],
      },
    ],
  })

  fs.writeFileSync(
    path.join(AUTH_DIR, 'admin.json'),
    JSON.stringify(makeStorageState(admin_token), null, 2)
  )
  fs.writeFileSync(
    path.join(AUTH_DIR, 'developer.json'),
    JSON.stringify(makeStorageState(developer_token), null, 2)
  )

  console.log('[global-setup] storageState files written to', AUTH_DIR)
}
