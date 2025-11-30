"""
PetAvatar Agent - Main orchestration for pet-to-human avatar transformation.

This agent coordinates the multi-step workflow of analyzing pet images,
mapping personality to careers, generating avatars, and creating complete
professional identity packages.

Deployed to AWS Bedrock AgentCore Runtime.
"""

from strands import Agent
from strands.models.bedrock import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from tools import (
    analyze_pet_image,
    map_personality_to_career,
    generate_avatar_image,
    generate_identity_package,
)


# System prompt for the agent
SYSTEM_PROMPT = """You are an AI assistant that transforms pet photos into professional human avatars with complete career identities.

Your workflow is:
1. Analyze the pet image to extract species, breed, expression, and personality traits
2. Map the personality traits to an appropriate human profession and career level
3. Generate a photorealistic human avatar that matches the career profile
4. Create a complete professional identity package including name, bio, skills, and career trajectory

Be creative but believable. The goal is to capture the pet's essence in human form while creating a coherent professional identity.

Important guidelines:
- Always follow the workflow in order
- Use the personality analysis to inform career selection
- Ensure the avatar matches the career profile (attire, setting, etc.)
- Make the identity package feel authentic and professional
- The similarity score should reflect how well the pet's personality translates to the human identity

When you receive an image and job_id, execute all four steps and return the complete results."""


# Create the agent with Bedrock Claude model
agent = Agent(
    model=BedrockModel(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0", region_name="us-east-1"
    ),
    tools=[
        analyze_pet_image,
        map_personality_to_career,
        generate_avatar_image,
        generate_identity_package,
    ],
    system_prompt=SYSTEM_PROMPT,
)

# Initialize the AgentCore app
app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    AgentCore entrypoint for processing pet avatar requests.
    
    This is the main entry point invoked by AgentCore Runtime.
    It orchestrates the entire workflow from pet analysis to 
    final identity package generation.

    Args:
        payload: Dictionary containing:
            - image_base64: Base64 encoded pet image
            - job_id: Unique job identifier for tracking

    Returns:
        Dictionary containing:
        - job_id: The job identifier
        - status: Processing status
        - pet_analysis: Complete personality analysis (if successful)
        - career_profile: Mapped career information (if successful)
        - avatar_image_base64: Generated avatar image (if successful)
        - identity_package: Complete professional identity (if successful)
        - error: Error message (if failed)
    """
    try:
        image_base64 = payload.get("image_base64", "")
        job_id = payload.get("job_id", "unknown")
        
        if not image_base64:
            return {
                "job_id": job_id,
                "status": "failed",
                "error": "No image_base64 provided in payload"
            }
        
        # Invoke the agent with the image and job context
        user_message = f"""Please process this pet image (job_id: {job_id}) through the complete avatar generation workflow:

1. First, analyze the pet image to extract personality traits using the analyze_pet_image tool
2. Then, map the personality to an appropriate career using the map_personality_to_career tool
3. Next, generate a professional avatar image using the generate_avatar_image tool
4. Finally, create the complete identity package using the generate_identity_package tool

The base64 encoded image data is provided below. Please execute all steps and provide the complete results.

Image data: {image_base64}"""

        # Run the agent
        result = agent(user_message)
        
        return {
            "job_id": job_id,
            "status": "completed",
            "response": str(result.message) if hasattr(result, 'message') else str(result)
        }
        
    except Exception as e:
        return {
            "job_id": payload.get("job_id", "unknown"),
            "status": "failed",
            "error": str(e)
        }


# For local testing without AgentCore
if __name__ == "__main__":
    app.run()
