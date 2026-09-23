# A note from the author (this is the only non-AI written thing in this whole project)
Hey humans! The readme.md file is wordy isn't it! And there's advanced.md which has even more words. I've left as is, as it's probably useful for LLMs. TBH As your set up is likely to be different to mine I'd do this:

1. Set up BirdnetGo and Fugleramme however you want. 
2. Once Fugleramme is running, rather than run setup.py, point your friendly LLM at this repo and ask it to provide you the prompts and files in order to get it running for your set up and TV.
3. Do as you are told.
4. See your local birdlife on screen.

As per the heading - this is all vibe coded and was originally intended for my own personal amusement only. Further vibe coding has made it more configurable and now theres a fancy setup thingy to keep things simple.

I am reasonably technical but I haven't done a security audit on this or really read much of the code. 

Also note that currently Fugleramme doesn't support the Frame TVs native resolution of 3840x2160. In the admin page I've chosen 4k resolution and a margin of 13%. This will mean you can't choose a matte for the image. If Fugleramme does start to support native resolutions I think it is possible to change this script to preserve the matte on each update, but for now that doesn't happen.

**Project update (0.2.0):** The note above describes the original setup. FrameSync now carries a matte to the next collage when the TV reports complete matte metadata for the currently displayed FrameSync image. Whether a matte can be chosen still depends on the image and TV model.

I hope this is useful and brings as much joy to you as it has for me. Thanks so much to the creators of Birdnet and Fugleramme. This project is a small pebble sitting on the shoulder of giants.
