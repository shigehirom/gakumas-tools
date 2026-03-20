import { MongoClient } from "mongodb";
(async () => {
    if (!process.env.MONGODB_URI) {
        console.error("MONGODB_URI not set.");
        process.exit(1);
    }
    const client = new MongoClient(process.env.MONGODB_URI);
    await client.connect();
    const db = client.db(process.env.MONGODB_DB || "gakumas-tools");
    const result = await db.collection("loadouts").deleteMany({});
    console.log(`Deleted ${result.deletedCount} loadouts.`);
    await client.close();
})();
