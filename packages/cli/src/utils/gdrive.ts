import { google } from 'googleapis';
import * as fs from 'fs';
import * as path from 'path';
import * as readline from 'readline';
import * as os from 'os';
// import { OAuth2Client } from 'google-auth-library'; // Version mismatch in monorepo

const SCOPES = ['https://www.googleapis.com/auth/drive.file'];
const TOKEN_DIR = path.join(os.homedir(), '.config', 'gakumas-tools');
const TOKEN_PATH = path.join(TOKEN_DIR, 'tokens.json');

export class GoogleDriveClient {
    private static auth: any = null;

    static async init() {
        if (this.auth) return;

        const clientId = process.env.GOOGLE_CLIENT_ID;
        const clientSecret = process.env.GOOGLE_CLIENT_SECRET;

        if (!clientId || !clientSecret) {
            console.error('GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is not set in .env.local');
            return;
        }

        const oAuth2Client = new google.auth.OAuth2(
            clientId,
            clientSecret,
            'urn:ietf:wg:oauth:2.0:oob' // For CLI apps
        );

        // Check if we have previously stored a token.
        try {
            if (fs.existsSync(TOKEN_PATH)) {
                const token = fs.readFileSync(TOKEN_PATH, 'utf-8');
                oAuth2Client.setCredentials(JSON.parse(token));
                this.auth = oAuth2Client;
                return;
            }
        } catch (e) {
            console.warn('Error reading stored token, requesting new one...');
        }

        try {
            await this.getNewToken(oAuth2Client);
            this.auth = oAuth2Client;
        } catch (err: any) {
            console.error('Failed to initialize Google Drive client auth:', err.message);
        }
    }

    private static async getNewToken(oAuth2Client: any): Promise<void> {
        if (!process.stdin.isTTY) {
            throw new Error('Google Drive authentication is required, but the terminal is non-interactive (non-TTY). Please run the command manually from an interactive shell once to authenticate.');
        }

        const authUrl = oAuth2Client.generateAuthUrl({
            access_type: 'offline',
            scope: SCOPES,
        });

        console.log('\nAuthorize this app by visiting this url:');
        console.log(authUrl);
        console.log('\n');

        const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout,
        });

        return new Promise((resolve, reject) => {
            rl.question('Enter the code from that page here: ', async (code) => {
                rl.close();
                try {
                    const { tokens } = await oAuth2Client.getToken(code);
                    oAuth2Client.setCredentials(tokens);

                    // Save tokens
                    if (!fs.existsSync(TOKEN_DIR)) {
                        fs.mkdirSync(TOKEN_DIR, { recursive: true });
                    }
                    fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens));
                    console.log('Token stored to', TOKEN_PATH);
                    resolve();
                } catch (err) {
                    console.error('Error retrieving access token', err);
                    reject(err);
                }
            });
        });
    }

    static async uploadFile(fileName: string, content: string): Promise<string | undefined> {
        const folderId = process.env.GOOGLE_DRIVE_FOLDER_ID;
        if (!folderId) {
            console.error('GOOGLE_DRIVE_FOLDER_ID is not set.');
            return undefined;
        }

        if (!this.auth) {
            await this.init();
            if (!this.auth) return undefined; // Init failed
        }

        const drive = google.drive({ version: 'v3', auth: this.auth! });

        const fileMetadata = {
            name: fileName,
            parents: [folderId],
        };

        const media = {
            mimeType: 'text/plain',
            body: content,
        };

        try {
            // Check if file exists
            const listRes: any = await drive.files.list({
                q: `'${folderId}' in parents and name = '${fileName}' and trashed = false`,
                fields: 'files(id, name)',
                spaces: 'drive',
            });

            const existingFiles = listRes.data.files;
            const isDebug = process.argv.includes('--debug');

            let file;
            if (existingFiles && existingFiles.length > 0) {
                const targetFile = existingFiles[0];
                if (isDebug) console.log(`Found existing file ${fileName} (ID: ${targetFile.id}). Updating content...`);
                
                // Update existing file content
                file = await drive.files.update({
                    fileId: targetFile.id!,
                    media: media,
                    fields: 'id, webViewLink',
                });
                
                // If there are duplicate files, clean them up
                if (existingFiles.length > 1) {
                    if (isDebug) console.log(`Found ${existingFiles.length - 1} duplicate files. Deleting them...`);
                    for (let i = 1; i < existingFiles.length; i++) {
                        await drive.files.delete({ fileId: existingFiles[i].id! });
                    }
                }
            } else {
                // Create new file
                if (isDebug) console.log(`Uploading new file ${fileName} to Google Drive (Folder ID: ${folderId})...`);
                file = await drive.files.create({
                    requestBody: fileMetadata,
                    media: media,
                    fields: 'id, webViewLink',
                });
            }

            if (isDebug) console.log('File Uploaded/Updated. Id:', file.data.id);
            return file.data.webViewLink || undefined;

        } catch (err: any) {
            console.error('Upload failed:', err.message);
            if (err.message.includes('invalid_grant')) {
                console.warn('Authentication token is invalid (invalid_grant). Clearing token file...');
                try {
                    if (fs.existsSync(TOKEN_PATH)) {
                        fs.unlinkSync(TOKEN_PATH);
                        console.warn('Token file removed. Please rerun the command to re-authenticate.');
                    }
                } catch (unlinkErr: any) {
                    console.error('Failed to remove token file:', unlinkErr.message);
                }
            }
            return undefined;
        }
    }
}
