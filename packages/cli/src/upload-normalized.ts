
import { GoogleDriveClient } from './utils/gdrive';
import * as path from 'path';
import * as fs from 'fs';

// Load .env.local manually
// Note: This script is in packages/cli/src/
const envPath = path.resolve(__dirname, '../../../gakumas-tools/.env.local');

console.log(`Loading environment from ${envPath}`);
if (fs.existsSync(envPath)) {
    const content = fs.readFileSync(envPath, 'utf-8');
    content.split('\n').forEach(line => {
        const match = line.match(/^([^=]+)=(.*)$/);
        if (match) {
            const key = match[1].trim();
            const val = match[2].trim().replace(/^["'](.*)["']$/, '$1');
            if (!process.env[key]) {
                process.env[key] = val;
            }
        }
    });
} else {
    console.error('Could not find .env.local at ' + envPath);
    process.exit(1);
}

const MD_DIR = path.resolve(__dirname, '../../../local/export/md');

async function run() {
    console.log(`--- Uploading Markdown files from ${MD_DIR} to Google Drive ---`);
    
    if (!fs.existsSync(MD_DIR)) {
        console.error(`Directory not found: ${MD_DIR}`);
        return;
    }

    const files = fs.readdirSync(MD_DIR).filter(f => f.endsWith('.md'));
    console.log(`Found ${files.length} files to upload.`);

    await GoogleDriveClient.init();

    for (const file of files) {
        const filePath = path.join(MD_DIR, file);
        const content = fs.readFileSync(filePath, 'utf-8');
        
        console.log(`Uploading ${file}...`);
        try {
            await GoogleDriveClient.uploadFile(file, content);
            console.log(`Successfully uploaded ${file}`);
        } catch (e: any) {
            console.error(`Failed to upload ${file}:`, e.message);
        }
    }

    console.log('All uploads completed.');
}

run();
