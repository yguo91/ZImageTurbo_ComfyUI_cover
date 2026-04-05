import copy
from pydantic import BaseModel, Field


class GenerationParams(BaseModel):
    prompt: str
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    seed: int = Field(default=0, ge=0, le=4294967295)
    steps: int = Field(default=9, ge=1, le=50)
    pixel_art: bool = False
    filename_prefix: str = Field(default="z-image", max_length=64)


# Pre-converted API format derived from reference/image_z_image_turbo.json.
# Connections are represented as [src_node_id_str, output_slot_index].
WORKFLOW_API_TEMPLATE: dict = {
    "39": {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": "qwen_3_4b.safetensors",
            "type": "lumina2",
            "device": "default",
        },
    },
    "40": {
        "class_type": "VAELoader",
        "inputs": {"vae_name": "ae.safetensors"},
    },
    "41": {
        "class_type": "EmptySD3LatentImage",
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
    },
    "42": {
        "class_type": "ConditioningZeroOut",
        "inputs": {"conditioning": ["45", 0]},
    },
    "43": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["44", 0], "vae": ["40", 0]},
    },
    "44": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["47", 0],
            "positive": ["45", 0],
            "negative": ["42", 0],
            "latent_image": ["41", 0],
            "seed": 0,
            "steps": 9,
            "cfg": 1.0,
            "sampler_name": "res_multistep",
            "scheduler": "simple",
            "denoise": 1.0,
        },
    },
    "45": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["39", 0], "text": ""},
    },
    "46": {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": "z_image_turbo_bf16.safetensors",
            "weight_dtype": "default",
        },
    },
    "47": {
        # model input points to node 48 (LoRA) by default;
        # build_api_prompt rewires this when pixel_art=False
        "class_type": "ModelSamplingAuraFlow",
        "inputs": {"model": ["48", 0], "shift": 3.0},
    },
    "48": {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": ["46", 0],
            "lora_name": "pixel_art_style_z_image_turbo.safetensors",
            "strength_model": 1.0,
        },
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"images": ["43", 0], "filename_prefix": "z-image"},
    },
}


def build_api_prompt(params: GenerationParams) -> dict:
    """Deep-copy the template and inject user-controlled parameters."""
    workflow = copy.deepcopy(WORKFLOW_API_TEMPLATE)

    workflow["45"]["inputs"]["text"] = params.prompt
    workflow["41"]["inputs"]["width"] = params.width
    workflow["41"]["inputs"]["height"] = params.height
    workflow["44"]["inputs"]["seed"] = params.seed
    workflow["44"]["inputs"]["steps"] = params.steps
    workflow["9"]["inputs"]["filename_prefix"] = params.filename_prefix

    if params.pixel_art:
        # Route model through the LoRA node
        workflow["47"]["inputs"]["model"] = ["48", 0]
    else:
        # Remove the LoRA node entirely and bypass directly to UNETLoader output
        del workflow["48"]
        workflow["47"]["inputs"]["model"] = ["46", 0]

    return workflow
