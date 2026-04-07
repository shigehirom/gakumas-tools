import { getServerSession } from "next-auth/next";
import { authOptions } from "@/utils/auth";
import { connect } from "@/utils/mongodb";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session) {
    return new Response("Unauthorized", { status: 401 });
  }
  const userId = session.user.id;

  const { db } = await connect();
  const memories =
    (await db.collection("memories").find({ userId }).toArray()) || [];

  return Response.json({ memories });
}

export async function POST(request) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return new Response("Unauthorized", { status: 401 });
  }
  const userId = session.user.id;

  const { memories } = await request.json();

  const { db } = await connect();
  const now = new Date();
  const year = String(now.getFullYear()).slice(-2);
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  const prefix = `${year}/${month}/${day}＿`;

  const memoriesToInsert = memories.map(
    ({ name, pIdolId, params, pItemIds, skillCardIds, customizations }) => ({
      userId,
      name: `${prefix}${name}`,
      pIdolId,
      params,
      pItemIds,
      skillCardIds,
      customizations,
    })
  );

  const { insertedIds } = await db.collection("memories").insertMany(memoriesToInsert);

  return Response.json({ ids: insertedIds });
}
