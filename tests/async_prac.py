
import asyncio

async def greet(name):
    print("Inside greet()")
    return f"Hello, {name}"

# Create a coroutine object
coro = greet("MCP")

print("Object:", coro)
print("Type:", type(coro))
print("Is coroutine:", asyncio.iscoroutine(coro))

# Actually execute the coroutine
result = asyncio.run(coro)

print("Result:", result)
