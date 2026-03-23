import { getServerSession } from "next-auth/next";
import { authOptions } from "@/utils/auth";
import { connect } from "@/utils/mongodb";
import { triggerAutomation } from "@/utils/automation";

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
  const memoriesToInsert = memories.map(
    ({ name, pIdolId, params, pItemIds, skillCardIds, customizations }) => ({
      userId,
      name,
      pIdolId,
      params,
      pItemIds,
      skillCardIds,
      customizations,
    })
  );

  const { insertedIds } = await db.collection("memories").insertMany(memoriesToInsert);

  // Trigger automation asynchronously
  triggerAutomation(memoriesToInsert).catch((err) => {
    console.error("Automation trigger failed:", err);
  });

  return Response.json({ ids: insertedIds });
}
