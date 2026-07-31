import asyncio
import logging
from reboot.aio.applications import Application
from patient_case_servicer import PatientCaseServicer
from bed_registry_servicer import BedRegistryServicer

logging.basicConfig(level=logging.INFO)

BED_REGISTRY_ID = "global"


async def main():
    application = Application(
        servicers=[PatientCaseServicer, BedRegistryServicer],
    )
    await application.run()


if __name__ == '__main__':
    asyncio.run(main())
